import asyncio
import json
import webbrowser
from pathlib import Path

import httpx2
from aiohttp import web

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.client.auth import OAuthClientProvider
from mcp.client.auth.oauth2 import TokenStorage
from mcp.shared.auth import OAuthClientMetadata


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
# Menu helpers
# ============================================================

def display_menu(result):

    print()
    print("===================================")
    print("          RESTAURANT MENU")
    print("===================================")
    print()

    if not result.structured_content:

        print(
            "No structured menu response."
        )

        return

    data = result.structured_content

    categories = data.get(
        "categories",
        []
    )

    if not categories:

        print(
            "No menu categories returned."
        )

        print()

        print(
            json.dumps(
                data,
                indent=2,
                default=str
            )
        )

        return

    for category in categories:

        category_name = (
            category.get("name")
            or category.get(
                "categoryName"
            )
            or "Category"
        )

        print(
            f"--- {category_name} ---"
        )

        items = category.get(
            "items",
            []
        )

        for item in items:

            item_name = (
                item.get("name")
                or item.get("itemName")
                or "Unknown item"
            )

            price = (
                item.get("price")
                or item.get("itemPrice")
                or "N/A"
            )

            veg = item.get(
                "isVeg",
                item.get(
                    "veg",
                    None
                )
            )

            veg_text = ""

            if veg is True:

                veg_text = " [VEG]"

            elif veg is False:

                veg_text = " [NON-VEG]"

            print(
                f"  • {item_name}"
                f" — ₹{price}"
                f"{veg_text}"
            )

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
                    # Ask what user wants
                    # ----------------------------------------

                    print()
                    print("===================================")
                    print("        WHAT ARE YOU CRAVING?")
                    print("===================================")
                    print()

                    query = input(
                        "Search for food: "
                    ).strip()

                    if not query:

                        print(
                            "Search query cannot be empty."
                        )

                        return

                    # ----------------------------------------
                    # Search restaurants
                    # ----------------------------------------

                    print()
                    print(
                        "Searching Swiggy..."
                    )

                    print()

                    search_arguments = {

                        "addressId": address_id,

                        "query": query,

                        "offset": 0,
                    }

                    restaurant_result = (
                        await session.call_tool(
                            "search_restaurants",
                            search_arguments
                        )
                    )

                    # ----------------------------------------
                    # Check tool error
                    # ----------------------------------------

                    if restaurant_result.is_error:

                        print()
                        print(
                            "Swiggy restaurant search failed."
                        )

                        print(
                            restaurant_result
                        )

                        return

                    # ----------------------------------------
                    # Extract restaurants
                    # ----------------------------------------

                    restaurants = (
                        extract_restaurants(
                            restaurant_result
                        )
                    )

                    # ----------------------------------------
                    # Display restaurants
                    # ----------------------------------------

                    open_restaurants = (
                        display_restaurants(
                            restaurants
                        )
                    )

                    if not open_restaurants:

                        return

                    # ----------------------------------------
                    # Choose restaurant
                    # ----------------------------------------

                    selected_restaurant = (
                        await choose_restaurant(
                            open_restaurants
                        )
                    )

                    if not selected_restaurant:

                        return

                    # ----------------------------------------
                    # Get restaurant ID
                    # ----------------------------------------

                    restaurant_id = (
                        get_restaurant_id(
                            selected_restaurant
                        )
                    )

                    if not restaurant_id:

                        print(
                            "Could not determine "
                            "restaurant ID."
                        )

                        print()

                        print(
                            "Restaurant response:"
                        )

                        print(
                            json.dumps(
                                selected_restaurant,
                                indent=2,
                                default=str
                            )
                        )

                        return

                    # ----------------------------------------
                    # Get restaurant menu
                    # ----------------------------------------

                    print()
                    print(
                        "Loading restaurant menu..."
                    )

                    print()

                    menu_arguments = {

                        "addressId": address_id,

                        "restaurantId": restaurant_id,

                        "page": 1,

                        "pageSize": 5,
                    }

                    menu_result = (
                        await session.call_tool(
                            "get_restaurant_menu",
                            menu_arguments
                        )
                    )

                    if menu_result.is_error:

                        print(
                            "Failed to retrieve menu."
                        )

                        print(
                            menu_result
                        )

                        return

                    # ----------------------------------------
                    # Display menu
                    # ----------------------------------------

                    display_menu(
                        menu_result
                    )

                    print()
                    print(
                        "==================================="
                    )
                    print(
                        "       SEASALT MVP MILESTONE"
                    )
                    print(
                        "==================================="
                    )
                    print()

                    print(
                        "✓ Swiggy OAuth"
                    )

                    print(
                        "✓ MCP connection"
                    )

                    print(
                        "✓ Location selection"
                    )

                    print(
                        "✓ Restaurant search"
                    )

                    print(
                        "✓ Restaurant selection"
                    )

                    print(
                        "✓ Restaurant menu"
                    )

                    print()

                    print(
                        "Next: connect Gemma to turn "
                        "the user's craving into a "
                        "personalized food quest."
                    )

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