import asyncio
import json
import re
import webbrowser
from pathlib import Path

import httpx2
from aiohttp import web

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.client.auth import OAuthClientProvider
from mcp.client.auth.oauth2 import TokenStorage
from mcp.shared.auth import OAuthClientMetadata

from gemma import GemmaService


# ============================================================
# Configuration
# ============================================================

SWIGGY_MCP_URL = "https://mcp.swiggy.com/food"

REDIRECT_URI = "http://localhost:3000/oauth/callback"

TOKEN_FILE = Path(".tokens.json")
CLIENT_FILE = Path(".client.json")


# ============================================================
# Local OAuth storage
# ============================================================

class FileTokenStorage(TokenStorage):

    def __init__(self):
        self.token_file = TOKEN_FILE
        self.client_file = CLIENT_FILE

    async def get_tokens(self):
        if not self.token_file.exists():
            return None

        from mcp.shared.auth import OAuthToken

        data = json.loads(
            self.token_file.read_text()
        )

        return OAuthToken(**data)

    async def set_tokens(self, tokens):

        self.token_file.write_text(
            tokens.model_dump_json(indent=2)
        )

    async def get_client_info(self):

        if not self.client_file.exists():
            return None

        from mcp.shared.auth import OAuthClientInformationFull

        data = json.loads(
            self.client_file.read_text()
        )

        return OAuthClientInformationFull(**data)

    async def set_client_info(self, client_info):

        self.client_file.write_text(
            client_info.model_dump_json(indent=2)
        )


# ============================================================
# OAuth callback server
# ============================================================

class OAuthCallbackServer:

    def __init__(self):
        self.future = None

    async def callback(self, request):

        code = request.query.get("code")
        state = request.query.get("state")
        error = request.query.get("error")

        print()
        print("OAuth callback received.")

        if error:

            print(f"OAuth error: {error}")

            if self.future and not self.future.done():

                self.future.set_exception(
                    RuntimeError(
                        f"OAuth authorization failed: {error}"
                    )
                )

            return web.Response(
                text="""
                <html>
                    <body>
                        <h2>Seasalt authentication failed.</h2>
                        <p>You can close this window.</p>
                    </body>
                </html>
                """,
                content_type="text/html",
            )

        if not code:

            return web.Response(
                text="Missing authorization code.",
                status=400,
            )

        if self.future and not self.future.done():

            self.future.set_result(
                {
                    "code": code,
                    "state": state,
                }
            )

        return web.Response(
            text="""
            <html>
                <body>
                    <h2>Seasalt authentication successful!</h2>
                    <p>You can close this browser window.</p>
                </body>
            </html>
            """,
            content_type="text/html",
        )

    async def start(self):

        app = web.Application()

        app.router.add_get(
            "/oauth/callback",
            self.callback,
        )

        runner = web.AppRunner(app)

        await runner.setup()

        site = web.TCPSite(
            runner,
            "localhost",
            3000,
        )

        await site.start()

        return runner

    async def wait_for_callback(self):

        self.future = (
            asyncio.get_running_loop()
            .create_future()
        )

        return await self.future


# ============================================================
# Address helpers
# ============================================================

def display_addresses(result):

    if not result.structured_content:

        print(
            "No structured response received."
        )

        return []

    addresses = result.structured_content.get(
        "addresses",
        []
    )

    if not addresses:

        print(
            "No saved addresses found."
        )

        return []

    print()
    print("===================================")
    print("       AVAILABLE LOCATIONS")
    print("===================================")
    print()

    for index, address in enumerate(
        addresses,
        start=1
    ):

        label = (
            address.get("addressTag")
            or address.get("addressCategory")
            or f"Location {index}"
        )

        print(
            f"{index}. {label}"
        )

    print()

    return addresses


async def choose_address(addresses):

    if not addresses:
        return None

    while True:

        try:

            choice = input(
                "Choose your location number: "
            ).strip()

            index = int(choice)

            if 1 <= index <= len(addresses):

                selected = addresses[index - 1]

                print()

                print(
                    f"Selected location: "
                    f"{selected.get('addressTag', index)}"
                )

                print()

                return selected

            print(
                f"Please enter a number between "
                f"1 and {len(addresses)}."
            )

        except ValueError:

            print(
                "Please enter a valid number."
            )


def get_address_id(address):

    return (
        address.get("id")
        or address.get("addressId")
        or address.get("address_id")
    )


# ============================================================
# Restaurant helpers
# ============================================================

def extract_restaurants(result):

    if not result.structured_content:

        print(
            "No structured restaurant response."
        )

        return []

    data = result.structured_content

    # Swiggy may return restaurants directly
    # or nested inside another field.
    restaurants = data.get(
        "restaurants",
        []
    )

    return restaurants


def display_restaurants(restaurants):

    if not restaurants:

        print()
        print(
            "No restaurants found."
        )

        return

    print()
    print("===================================")
    print("       AVAILABLE RESTAURANTS")
    print("===================================")
    print()

    open_restaurants = []

    for restaurant in restaurants:

        status = (
            restaurant.get(
                "availabilityStatus",
                "UNKNOWN"
            )
            .upper()
        )

        if status == "OPEN":

            open_restaurants.append(
                restaurant
            )

    if not open_restaurants:

        print(
            "No OPEN restaurants were found."
        )

        print(
            "Swiggy returned restaurants, "
            "but none are currently available."
        )

        return

    for index, restaurant in enumerate(
        open_restaurants,
        start=1
    ):

        name = (
            restaurant.get("name")
            or restaurant.get("restaurantName")
            or "Unknown restaurant"
        )

        rating = (
            restaurant.get("rating")
            or restaurant.get("avgRating")
            or "N/A"
        )

        distance = (
            restaurant.get("distanceKm")
            or restaurant.get("distance")
            or "N/A"
        )

        delivery_time = (
            restaurant.get("deliveryTime")
            or restaurant.get("deliveryTimeMinutes")
            or restaurant.get("sla")
            or "N/A"
        )

        print(
            f"{index}. {name}"
        )

        print(
            f"   Rating: {rating}"
        )

        print(
            f"   Distance: {distance} km"
        )

        print(
            f"   Delivery: {delivery_time}"
        )

        print()

    return open_restaurants


async def choose_restaurant(restaurants):

    if not restaurants:

        return None

    while True:

        try:

            choice = input(
                "Choose a restaurant number: "
            ).strip()

            index = int(choice)

            if 1 <= index <= len(restaurants):

                selected = restaurants[
                    index - 1
                ]

                name = (
                    selected.get("name")
                    or selected.get(
                        "restaurantName"
                    )
                    or "Unknown restaurant"
                )

                print()

                print(
                    f"Selected restaurant: "
                    f"{name}"
                )

                print()

                return selected

            print(
                f"Please enter a number between "
                f"1 and {len(restaurants)}."
            )

        except ValueError:

            print(
                "Please enter a valid number."
            )


def get_restaurant_id(restaurant):

    return (
        restaurant.get("restaurantId")
        or restaurant.get("id")
        or restaurant.get(
            "restaurant_id"
        )
    )


# ============================================================
# Menu extraction, validation, and adventure display
# ============================================================

def _first_present(mapping, *keys):
    """Return the first non-None, non-empty value from a mapping."""
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return value
    return None


def _numeric_value(value):
    """Convert a numeric or rupee-formatted value to float; otherwise None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        value = _first_present(value, "amount", "value", "price", "finalPrice")
        if value is None:
            return None
    match = re.search(r"\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group()) if match else None


def _display_number(value):
    if value is None:
        return None
    return int(value) if float(value).is_integer() else round(float(value), 2)


def _extract_menu_items(categories):
    """Flatten simple and nested Swiggy menu categories into menu items."""
    items = []

    def visit_category(category):
        if not isinstance(category, dict):
            return

        category_items = category.get("items", [])
        if isinstance(category_items, list):
            for item in category_items:
                if not isinstance(item, dict):
                    continue

                name = _first_present(item, "name", "itemName", "title")
                price_value = _first_present(
                    item, "price", "itemPrice", "finalPrice", "defaultPrice"
                )
                price = _numeric_value(price_value)
                veg = item.get("isVeg", item.get("veg"))

                if name:
                    items.append({
                        "name": str(name).strip(),
                        "price": _display_number(price),
                        "isVeg": veg if isinstance(veg, bool) else None,
                    })

        for child_key in ("subcategories", "categories", "children"):
            children = category.get(child_key, [])
            if isinstance(children, list):
                for child in children:
                    visit_category(child)

    if isinstance(categories, list):
        for category in categories:
            visit_category(category)

    # Avoid duplicate entries if a nested response repeats an item.
    unique = []
    seen = set()
    for item in items:
        key = (item["name"].casefold(), item["price"], item["isVeg"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _restaurant_distance(restaurant):
    value = _first_present(restaurant, "distanceKm", "distance")
    distance = _numeric_value(value)
    return _display_number(distance)


def _restaurant_name(restaurant):
    return str(
        _first_present(restaurant, "name", "restaurantName")
        or "Unknown restaurant"
    )


def _restaurant_id(restaurant):
    value = _first_present(restaurant, "restaurantId", "id", "restaurant_id")
    return str(value) if value is not None else None


def _build_restaurant_payload(restaurant, menu_result):
    """Create a compact, normalized payload for Gemma from real Swiggy data."""
    data = menu_result.structured_content or {}
    categories = data.get("categories", [])
    menu_items = _extract_menu_items(categories)

    # We need a real price to validate a generated stop and its total cost.
    menu_items = [item for item in menu_items if item["price"] is not None]

    return {
        "name": _restaurant_name(restaurant),
        "restaurantId": _restaurant_id(restaurant),
        "availabilityStatus": str(
            restaurant.get("availabilityStatus", "UNKNOWN")
        ).upper(),
        "distanceKm": _restaurant_distance(restaurant),
        "menu": menu_items,
    }


def validate_route_plan(plan, restaurant_data, craving_profile):
    """Validate Gemma's choices against Swiggy data and recalculate totals."""
    warnings = list(plan.get("warnings") or [])
    if not isinstance(warnings, list):
        warnings = [str(warnings)]

    restaurants_by_id = {
        str(restaurant.get("restaurantId")): restaurant
        for restaurant in restaurant_data
        if restaurant.get("restaurantId") is not None
    }
    requested_stops = _numeric_value(craving_profile.get("stops")) or 3
    requested_stops = max(1, int(requested_stops))
    budget = _numeric_value(craving_profile.get("budget_inr"))

    max_distance = _numeric_value(
        craving_profile.get("max_distance_km")
    )

    validated_stops = []
    for stop in plan.get("stops", []):
        if not isinstance(stop, dict):
            warnings.append("A malformed stop from the generated plan was removed.")
            continue

        restaurant_id = stop.get("restaurant_id")
        restaurant = restaurants_by_id.get(str(restaurant_id))
        if not restaurant or restaurant.get("availabilityStatus") != "OPEN":
            warnings.append(
                f"Removed stop {stop.get('stop_number', '?')}: restaurant was not verified as OPEN in the supplied Swiggy data."
            )
            continue

        # Enforce the user's maximum distance using Swiggy data.
        distance = _numeric_value(restaurant.get("distanceKm"))

        if max_distance is not None:
            if distance is None:
                warnings.append(
                    f"Removed {restaurant['name']}: distance could not be verified."
                )
                continue

            if distance > max_distance:
                warnings.append(
                    f"Removed {restaurant['name']}: "
                    f"{_display_number(distance)} km exceeds "
                    f"your {_display_number(max_distance)} km limit."
                )
                continue

        requested_name = str(stop.get("dish_name") or "").strip().casefold()
        menu_item = next(
            (item for item in restaurant.get("menu", [])
             if str(item.get("name", "")).strip().casefold() == requested_name),
            None,
        )
        if not menu_item:
            warnings.append(
                f"Removed a dish from {restaurant['name']} because it was not found in the fetched menu."
            )
            continue

        price = _numeric_value(menu_item.get("price"))
        if price is None:
            warnings.append(
                f"Removed {menu_item['name']} because its price could not be verified."
            )
            continue

        validated_stops.append({
            "stop_number": len(validated_stops) + 1,
            "restaurant_name": restaurant["name"],
            "restaurant_id": str(restaurant["restaurantId"]),
            "dish_name": menu_item["name"],
            "price_inr": _display_number(price),
            "distance_km": restaurant.get("distanceKm"),
            "reason": str(stop.get("reason") or "Selected to match your craving."),
            "clue": str(stop.get("clue") or "Follow your craving to the next stop."),
        })

    if len(validated_stops) > requested_stops:
        validated_stops = validated_stops[:requested_stops]
        warnings.append(f"Limited the adventure to your requested {requested_stops} stops.")

    # Enforce the budget using verified menu prices, not Gemma's arithmetic.
    if budget is not None:
        while validated_stops and sum(
            float(stop["price_inr"]) for stop in validated_stops
        ) > budget:
            removed = validated_stops.pop()
            warnings.append(
                f"Removed {removed['dish_name']} to keep the verified food total within your ₹{_display_number(budget)} budget."
            )

    total = sum(float(stop["price_inr"]) for stop in validated_stops)
    total = _display_number(total)
    remaining = _display_number(budget - float(total)) if budget is not None else None

    if not validated_stops:
        warnings.append(
            "No stops survived validation. Try a broader craving or a higher budget."
        )

    return {
        "title": str(plan.get("title") or "Your Seasalt Adventure"),
        "summary": str(plan.get("summary") or "A food adventure built from available Swiggy menu data."),
        "stops": validated_stops,
        "total_food_cost_inr": total,
        "remaining_budget_inr": remaining,
        "warnings": list(dict.fromkeys(warnings)),
    }

def check_preference_coverage(plan, craving_profile):
    """Check whether the validated adventure covers the user's preferences."""

    stops = plan.get("stops", [])
    warnings = plan.setdefault("warnings", [])

    flavors = [
        str(value).casefold()
        for value in craving_profile.get("flavors", [])
    ]

    food_types = [
        str(value).casefold()
        for value in craving_profile.get("food_types", [])
    ]

    selected_dishes = [
        stop.get("dish_name", "").casefold()
        for stop in stops
    ]

    all_dishes = " ".join(selected_dishes)

    print("\nPreference coverage:")

    # Check requested flavors using dish names as a basic indicator.
    # This is a heuristic, not proof of a dish's flavor.
    flavor_keywords = {
        "spicy": ["spicy", "chilli", "chili", "hot", "schezwan"],
        "sweet": [
            "sweet", "chocolate", "choco", "cake", "pastry",
            "lava", "dessert", "mousse", "barfi", "brownie",
        ],
        "sour": ["sour", "tangy", "lemon", "tamarind"],
        "cheesy": ["cheese", "cheesy"],
        "crunchy": ["crispy", "crunchy", "crunch"],
    }

    for flavor in flavors:
        keywords = flavor_keywords.get(flavor, [flavor])

        found = any(
            keyword in dish
            for keyword in keywords
            for dish in selected_dishes
        )

        status = "Found" if found else "Not confirmed"
        print(f"  {flavor.title()}: {status}")

        if not found:
            warnings.append(
                f"Could not confirm a {flavor} dish from the selected menu items."
            )

    # Drinks must be supported by the actual selected menu item.
    if "drink" in food_types or "drinks" in food_types:
        drink_keywords = [
            "drink", "juice", "water", "soda", "cola",
            "sprite", "pepsi", "coke", "lemonade", "shake",
            "smoothie", "lassi", "tea", "coffee", "mojito",
        ]

        has_drink = any(
            keyword in dish
            for keyword in drink_keywords
            for dish in selected_dishes
        )

        print(
            f"  Drink: {'Found' if has_drink else 'Not found'}"
        )

        if not has_drink:
            warnings.append(
                "Your adventure does not include a verified drink."
            )

    # Report the number of stops.
    requested_stops = _numeric_value(
        craving_profile.get("stops")
    ) or 3

    print(f"  Stops: {len(stops)} of {int(requested_stops)} requested")

    if len(stops) < requested_stops:
        warnings.append(
            f"Only {len(stops)} suitable stops were found; "
            f"you requested {int(requested_stops)}."
        )

    # Deduplicate warnings.
    plan["warnings"] = list(dict.fromkeys(warnings))

    return plan

def display_adventure(plan):
    print()
    print("=" * 52)
    print(f"  {plan['title']}")
    print("=" * 52)
    print(plan["summary"])
    print()

    for stop in plan["stops"]:
        print(f"STOP {stop['stop_number']}: {stop['dish_name']}")
        print(f"  Restaurant: {stop['restaurant_name']}")
        print(f"  Price: ₹{stop['price_inr']}")
        if stop.get("distance_km") is not None:
            print(f"  Distance: {stop['distance_km']} km (as returned by Swiggy)")
        print(f"  Why this stop: {stop['reason']}")
        print(f"  Clue: {stop['clue']}")
        print()

    print("=" * 52)
    print(f"Verified food total: ₹{plan['total_food_cost_inr']}")
    if plan.get("remaining_budget_inr") is not None:
        print(f"Budget remaining: ₹{plan['remaining_budget_inr']}")

    if plan.get("warnings"):
        print("\nNotes:")
        for warning in plan["warnings"]:
            print(f"  - {warning}")
    print()


# ============================================================
# Main
# ============================================================

async def main():

    print()
    print("===================================")
    print("        SEASALT SWIGGY MCP")
    print("===================================")
    print()

    # --------------------------------------------------------
    # OAuth callback server
    # --------------------------------------------------------

    callback_server = OAuthCallbackServer()

    runner = await callback_server.start()

    print(
        "OAuth callback server running:"
    )

    print(
        f"  {REDIRECT_URI}"
    )

    print()

    # --------------------------------------------------------
    # OAuth metadata
    # --------------------------------------------------------

    storage = FileTokenStorage()

    metadata = OAuthClientMetadata(

        client_name="Seasalt",

        redirect_uris=[
            REDIRECT_URI
        ],

        response_types=[
            "code"
        ],

        grant_types=[
            "authorization_code"
        ],

        token_endpoint_auth_method="none",

        scope=(
            "mcp:tools "
            "mcp:resources "
            "mcp:prompts"
        ),
    )

    # --------------------------------------------------------
    # Browser redirect
    # --------------------------------------------------------

    async def redirect_handler(url: str):

        print()
        print("===================================")
        print("     SWIGGY AUTHENTICATION")
        print("===================================")
        print()

        print(
            "Opening browser for Swiggy login..."
        )

        print()

        print(
            "If the browser does not open,"
        )

        print(
            "copy this URL manually:"
        )

        print()

        print(url)

        print()

        webbrowser.open(url)

    # --------------------------------------------------------
    # OAuth callback
    # --------------------------------------------------------

    async def callback_handler():

        result = (
            await callback_server
            .wait_for_callback()
        )

        from mcp.shared.auth import (
            AuthorizationCodeResult
        )

        return AuthorizationCodeResult(

            code=result["code"],

            state=result["state"],
        )

    # --------------------------------------------------------
    # OAuth provider
    # --------------------------------------------------------

    auth_provider = OAuthClientProvider(

        server_url=SWIGGY_MCP_URL,

        client_metadata=metadata,

        storage=storage,

        redirect_handler=redirect_handler,

        callback_handler=callback_handler,
    )

    try:

        # ----------------------------------------------------
        # HTTP client
        # ----------------------------------------------------

        print(
            "Connecting to Swiggy Food MCP..."
        )

        print()

        async with httpx2.AsyncClient(
            auth=auth_provider,
            follow_redirects=True,
        ) as http_client:

            # ------------------------------------------------
            # MCP connection
            # ------------------------------------------------

            async with streamable_http_client(

                SWIGGY_MCP_URL,

                http_client=http_client,

            ) as streams:

                read_stream, write_stream = streams

                # --------------------------------------------
                # MCP session
                # --------------------------------------------

                async with ClientSession(

                    read_stream,

                    write_stream,

                ) as session:

                    print(
                        "Initializing MCP session..."
                    )

                    await session.initialize()

                    print()
                    print(
                        "==================================="
                    )
                    print(
                        "       MCP CONNECTION SUCCESS"
                    )
                    print(
                        "==================================="
                    )
                    print()

                    # ----------------------------------------
                    # List tools
                    # ----------------------------------------

                    tools_result = (
                        await session.list_tools()
                    )

                    print(
                        "Available Swiggy tools:"
                    )

                    print()

                    for tool in tools_result.tools:

                        print(
                            f"  - {tool.name}"
                        )

                    print()

                    # ----------------------------------------
                    # Get addresses
                    # ----------------------------------------

                    print(
                        "Calling get_addresses()..."
                    )

                    print()

                    address_result = (
                        await session.call_tool(
                            "get_addresses",
                            {}
                        )
                    )

                    addresses = display_addresses(
                        address_result
                    )

                    if not addresses:

                        return

                    # ----------------------------------------
                    # Choose location
                    # ----------------------------------------

                    selected_address = (
                        await choose_address(
                            addresses
                        )
                    )

                    if not selected_address:

                        return

                    address_id = get_address_id(
                        selected_address
                    )

                    if not address_id:

                        print(
                            "Could not determine "
                            "the selected address ID."
                        )

                        return

                    # ----------------------------------------
                    # Initialize Gemma and parse the craving
                    # ----------------------------------------

                    print()
                    print("===================================")
                    print("       SEASALT FOOD ADVENTURE")
                    print("===================================")
                    print()
                    user_craving = input(
                        "What are you craving? Include budget and time if you have limits: "
                    ).strip()

                    if not user_craving:
                        print("Please describe what you are craving.")
                        return

                    gemma = GemmaService()

                    print("\nGemma is understanding your craving...")
                    craving_profile = gemma.parse_craving(user_craving)
                    print("\nCraving profile:")
                    print(json.dumps(craving_profile, indent=2, ensure_ascii=False))

                    # Search using multiple short queries to discover more restaurants.
                    search_queries = [
                        str(craving_profile.get("craving") or user_craving).strip()
                    ]

                    flavors = craving_profile.get("flavors", [])
                    food_types = craving_profile.get("food_types", [])

                    for flavor in flavors:
                        query = str(flavor).strip()
                        if query and query not in search_queries:
                            search_queries.append(query)

                    for food_type in food_types:
                        query = str(food_type).strip()
                        if query and query not in search_queries:
                            search_queries.append(query)

                    # Keep the search manageable.
                    search_queries = search_queries[:3]

                    print("\nSearching Swiggy for restaurants...")

                    all_restaurants = []
                    seen_restaurant_ids = set()

                    for query in search_queries:
                        print(f"  Searching: {query}")

                        result = await session.call_tool(
                            "search_restaurants",
                            {
                                "addressId": address_id,
                                "query": query,
                                "offset": 0,
                            },
                        )

                        if result.is_error:
                            print(f"  Search failed for: {query}")
                            continue

                        for restaurant in extract_restaurants(result):
                            restaurant_id = _restaurant_id(restaurant)

                            if restaurant_id is None:
                                continue

                            restaurant_id = str(restaurant_id)

                            if restaurant_id in seen_restaurant_ids:
                                continue

                            seen_restaurant_ids.add(restaurant_id)
                            all_restaurants.append(restaurant)

                    # Only consider restaurants explicitly marked OPEN.
                    open_restaurants = [
                        restaurant
                        for restaurant in all_restaurants
                        if str(
                            restaurant.get("availabilityStatus", "")
                        ).upper() == "OPEN"
                    ]

                    if not open_restaurants:
                        print("No OPEN restaurants were found.")
                        return

                    # Prioritize restaurants within the requested distance.
                    max_distance = _numeric_value(
                        craving_profile.get("max_distance_km")
                    )

                    if max_distance is not None:
                        nearby_restaurants = []

                        for restaurant in open_restaurants:
                            distance = _numeric_value(
                                _restaurant_distance(restaurant)
                            )

                            if distance is not None and distance <= max_distance:
                                nearby_restaurants.append(restaurant)

                        print(
                            f"Found {len(open_restaurants)} open restaurants; "
                            f"{len(nearby_restaurants)} have verified distances "
                            f"within {max_distance} km."
                        )

                        open_restaurants = nearby_restaurants

                    # Fetch menus for up to eight eligible restaurants.
                    candidate_restaurants = open_restaurants[:8]

                    if not candidate_restaurants:
                        print(
                            "No restaurants with verified distances satisfy "
                            "your distance limit. Try increasing the distance "
                            "or searching again later."
                        )
                        return

                    restaurant_data = []

                    # Fetch real menus for a small candidate set to keep the
                    # first MVP responsive and limit MCP calls.
                    candidate_restaurants = open_restaurants[:5]
                    restaurant_data = []

                    for index, restaurant in enumerate(candidate_restaurants, start=1):
                        name = _restaurant_name(restaurant)
                        restaurant_id = _restaurant_id(restaurant)
                        print(
                            f"Fetching menu {index}/{len(candidate_restaurants)}: {name}..."
                        )

                        menu_result = await session.call_tool(
                            "get_restaurant_menu",
                            {
                                "addressId": address_id,
                                "restaurantId": restaurant_id,
                                "page": 1,
                                "pageSize": 8,
                            },
                        )

                        if menu_result.is_error:
                            print(f"  Skipped {name}: Swiggy menu request failed.")
                            continue

                        normalized = _build_restaurant_payload(
                            restaurant,
                            menu_result,
                        )
                        if normalized["menu"]:
                            restaurant_data.append(normalized)
                        else:
                            print(f"  No priced menu items found for {name}; skipped.")

                    if not restaurant_data:
                        print(
                            "Could not fetch any menus with verifiable prices. "
                            "Try again or broaden your craving."
                        )
                        return

                    print("\nGemma is creating your food adventure...")
                    raw_plan = gemma.generate_route_plan(
                        craving_profile,
                        restaurant_data,
                    )

                    # Validate all choices and recalculate totals in Python.
                    final_plan = validate_route_plan(
                        raw_plan,
                        restaurant_data,
                        craving_profile,
                    )

                    final_plan = check_preference_coverage(
                        final_plan,
                        craving_profile,
                    )

                    display_adventure(final_plan)

                    print("Seasalt MVP status:")
                    print("  ✓ Swiggy OAuth and MCP connection")
                    print("  ✓ Location selection")
                    print("  ✓ Gemma craving parsing")
                    print("  ✓ Live restaurant search")
                    print("  ✓ Real menu retrieval")
                    print("  ✓ Gemma-generated food adventure")
                    print("  ✓ Python validation of restaurants, dishes, and prices")

    finally:

        await runner.cleanup()


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        print()
        print(
            "Seasalt stopped."
        )
