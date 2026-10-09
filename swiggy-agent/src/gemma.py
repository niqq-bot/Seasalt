import json
import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types


load_dotenv()


class GemmaService:

    def __init__(self):

        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is missing. "
                "Check your .env file."
            )

        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=60_000,
            ),
        )

        self.model = "gemma-4-26b-a4b-it"

    # ========================================================
    # Parse user's craving
    # ========================================================

    def parse_craving(self, user_input: str) -> dict:

        if not user_input or not user_input.strip():
            raise ValueError(
                "The craving description cannot be empty."
            )

        prompt = f"""
You are the craving parser for Seasalt.

Seasalt transforms food cravings into personalized
food adventures.

Extract the user's preferences and return exactly one
valid JSON object. Do not return a JSON array.

Use this exact structure:

{{
    "craving": "short description",
    "flavors": [],
    "food_types": [],
    "dietary_preferences": [],
    "budget_inr": null,
    "time_minutes": null,
    "max_distance_km": null,
    "stops": 3
}}

Rules:

1. Summarize the craving.
2. Extract flavors and textures such as spicy,
   sweet, sour, crunchy, and cheesy.
3. Extract explicitly requested foods or cuisines.
4. Extract explicitly mentioned dietary preferences.
5. budget_inr must be the total budget in INR,
   or null if unspecified.
6. Convert available time to minutes, or null
   if unspecified.
7. Extract a maximum distance in kilometres when
   the user explicitly specifies one; otherwise null.
8. Default stops to 3 unless the user specifies
   a different number.
9. Never invent user preferences or constraints.
10. Return exactly one JSON object.
11. Do not wrap the object in an array.

User message:
{json.dumps(user_input, ensure_ascii=False)}
"""

        response = self._generate_with_retry(
            prompt=prompt,
            temperature=0.2,
        )

        result = self._parse_json_response(response)

        required_fields = {
            "craving",
            "flavors",
            "food_types",
            "dietary_preferences",
            "budget_inr",
            "time_minutes",
            "max_distance_km",
            "stops",
        }

        missing_fields = required_fields - result.keys()

        if missing_fields:
            raise RuntimeError(
                "Gemma craving profile is missing fields: "
                f"{missing_fields}"
            )

        for field in (
            "flavors",
            "food_types",
            "dietary_preferences",
        ):
            if not isinstance(result[field], list):
                raise RuntimeError(
                    f"Gemma field '{field}' must be a list."
                )

        if not isinstance(result["craving"], str):
            raise RuntimeError(
                "Gemma field 'craving' must be a string."
            )

        for field in (
            "budget_inr",
            "time_minutes",
            "max_distance_km",
        ):
            value = result[field]

            if value is not None:
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or value < 0
                ):
                    raise RuntimeError(
                        f"Gemma field '{field}' must be "
                        "a non-negative number or null."
                    )

        stops = result["stops"]

        if (
            isinstance(stops, bool)
            or not isinstance(stops, int)
            or stops < 1
        ):
            raise RuntimeError(
                "Gemma field 'stops' must be a "
                "positive integer."
            )

        return result

    # ========================================================
    # Generate short Swiggy search queries
    # ========================================================

    def generate_search_queries(
        self,
        craving_profile: dict,
    ) -> list[str]:

        prompt = f"""
You generate short search queries for a food
restaurant search engine.

USER'S CRAVING PROFILE:
{json.dumps(craving_profile, ensure_ascii=False)}

Generate three short, distinct search queries
covering different parts of the craving.

Return exactly one JSON object:

{{
    "queries": [
        "spicy crispy snacks",
        "chocolate desserts",
        "cold drinks"
    ]
}}

Rules:

1. Each query must contain 2 to 5 words.
2. Use actual foods, cuisines, or food categories.
3. Do not include budgets, distances, or time limits.
4. Do not use conversational sentences.
5. Cover different parts of the craving.
6. Return JSON only.
"""

        response = self._generate_with_retry(
            prompt=prompt,
            temperature=0.2,
        )

        result = self._parse_json_response(response)

        queries = result.get("queries")

        if not isinstance(queries, list):
            raise RuntimeError(
                "Gemma did not return a list of search queries."
            )

        cleaned_queries = []

        for query in queries:
            if not isinstance(query, str):
                continue

            query = query.strip()

            if not query:
                continue

            if len(query.split()) > 5:
                continue

            if query not in cleaned_queries:
                cleaned_queries.append(query)

        if not cleaned_queries:
            raise RuntimeError(
                "Gemma did not generate any valid search queries."
            )

        return cleaned_queries[:3]

    # ========================================================
    # Generate personalized food route
    # ========================================================

    def generate_route_plan(
        self,
        craving_profile: dict,
        restaurant_data: list[dict],
    ) -> dict:

        budget = craving_profile.get("budget_inr")
        max_distance = craving_profile.get("max_distance_km")
        requested_stops = craving_profile.get("stops", 3)

        # Filter restaurants before sending data to Gemma.
        eligible_restaurants = []

        for restaurant in restaurant_data:
            if not isinstance(restaurant, dict):
                continue

            # Reject restaurants explicitly marked closed.
            status = str(
                restaurant.get("status")
                or restaurant.get("availability")
                or ""
            ).upper()

            if status and any(
                word in status
                for word in ("CLOSED", "UNAVAILABLE", "NOT AVAILABLE")
            ):
                continue

            # Enforce distance only when actual distance is available.
            distance = restaurant.get("distance_km")

            if distance is not None and max_distance is not None:
                try:
                    if float(distance) > float(max_distance):
                        continue
                except (TypeError, ValueError):
                    pass

            eligible_restaurants.append(restaurant)

        if not eligible_restaurants:
            return {
                "title": "Your Seasalt Adventure",
                "summary": (
                    "We couldn't find restaurants matching "
                    "your distance constraint."
                ),
                "stops": [],
                "total_food_cost_inr": 0,
                "remaining_budget_inr": budget,
                "warnings": [
                    "No eligible restaurant data was available."
                ],
            }

        # Limit the prompt size.
        eligible_restaurants = eligible_restaurants[:3]

        prompt = f"""
    You are Seasalt, a creative food adventure planner.

    USER PREFERENCES:
    {json.dumps(craving_profile, ensure_ascii=False)}

    AVAILABLE RESTAURANTS AND MENUS:
    {json.dumps(eligible_restaurants, ensure_ascii=False)}

    Create a short food adventure using ONLY the supplied data.

    Return exactly one JSON object with this structure:

    {{
      "title": "Adventure title",
      "summary": "One short sentence",
      "stops": [
        {{
          "stop_number": 1,
          "restaurant_name": "Exact restaurant name",
          "restaurant_id": "Exact restaurant ID",
          "dish_name": "Exact menu item",
          "price_inr": 100,
          "distance_km": null,
          "reason": "Short explanation",
          "clue": "Short playful clue"
        }}
      ],
      "total_food_cost_inr": 100,
      "remaining_budget_inr": 400,
      "warnings": []
    }}

    STRICT RULES:

    - Return JSON only. No Markdown or explanations.
    - Do not reveal your reasoning.
    - Never invent a restaurant, dish, ID, price, or distance.
    - Select only items present in the supplied menus.
    - Respect the budget of {budget if budget is not None else "unspecified"} INR.
    - Respect the maximum distance of {
        str(max_distance) + " km"
        if max_distance is not None
        else "unspecified"
    }.
    - Make at most {requested_stops} stops.
    - Prefer the requested flavor and food sequence.
    - If the data cannot satisfy every preference, return fewer stops.
    - Use null for unknown distances.
    - Calculate the total from the selected item prices.
    - Remaining budget equals budget minus total when a budget exists.
    - Keep reasons and clues under 15 words each.
    - Do not include explanations of your decision-making.
    """

        response = self._generate_with_retry(
            prompt=prompt,
            temperature=0.2,
            max_attempts=2,
        )

        result = self._parse_json_response(response)

        return result

    # ========================================================
    # Generate content with timeout and retry handling
    # ========================================================

    def _generate_with_retry(
        self,
        prompt: str,
        temperature: float,
        max_attempts: int = 2,
    ):
        last_error = None

        for attempt in range(max_attempts):
            start_time = time.perf_counter()

            try:
                print(
                    f"\nSending request to Gemma "
                    f"({attempt + 1}/{max_attempts})...",
                    flush=True,
                )
                print(
                    f"Prompt size: {len(prompt)} characters",
                    flush=True,
                )

                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=temperature,
                        response_mime_type="application/json",
                        max_output_tokens=2048,
                    ),
                )

                elapsed = time.perf_counter() - start_time

                print(
                    f"Gemma API call completed in "
                    f"{elapsed:.2f} seconds.",
                    flush=True,
                )

                if response.text and response.text.strip():
                    return response

                # Diagnose why the API returned no text.
                print(
                    "\nGemma returned an empty text response.",
                    flush=True,
                )

                print(
                    "Prompt feedback:",
                    getattr(response, "prompt_feedback", None),
                    flush=True,
                )

                candidates = getattr(response, "candidates", None)

                if candidates:
                    for index, candidate in enumerate(candidates):
                        print(
                            f"Candidate {index + 1}:",
                            flush=True,
                        )
                        print(
                            "Finish reason:",
                            getattr(candidate, "finish_reason", None),
                            flush=True,
                        )
                        print(
                            "Finish message:",
                            getattr(candidate, "finish_message", None),
                            flush=True,
                        )
                        print(
                            "Content:",
                            getattr(candidate, "content", None),
                            flush=True,
                        )
                else:
                    print(
                        "Gemma returned no candidates.",
                        flush=True,
                    )

                print(
                    "Usage metadata:",
                    getattr(response, "usage_metadata", None),
                    flush=True,
                )

                raise RuntimeError(
                    "Gemma returned no usable text. "
                    "Check the response diagnostics above."
                )

            except Exception as exc:
                last_error = exc

                elapsed = time.perf_counter() - start_time

                print(
                    f"\nGemma request failed after "
                    f"{elapsed:.2f} seconds.",
                    flush=True,
                )
                print(
                    f"Error: {type(exc).__name__}: {exc}",
                    flush=True,
                )

                if attempt < max_attempts - 1:
                    print(
                        "Retrying in 2 seconds...",
                        flush=True,
                    )
                    time.sleep(2)

        raise RuntimeError(
            f"Gemma request failed after {max_attempts} attempts."
        ) from last_error
    # ========================================================
    # Shared JSON response parser
    # ========================================================

    @staticmethod
    def _parse_json_response(response) -> dict:

        if not response.text:
            raise RuntimeError(
                "Gemma returned an empty response."
            )

        text = response.text.strip()

        # Handle Markdown code fences.
        if text.startswith("```"):
            lines = text.splitlines()

            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            text = "\n".join(lines).strip()

        try:
            result = json.loads(text)

        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Gemma returned invalid JSON:\n"
                f"{text}"
            ) from exc

        # Unwrap a single JSON object returned in an array.
        if isinstance(result, list):

            if (
                len(result) == 1
                and isinstance(result[0], dict)
            ):
                result = result[0]

            else:
                raise RuntimeError(
                    "Expected one JSON object, but Gemma "
                    f"returned a list containing {len(result)} "
                    "items.\n"
                    f"Actual response:\n{text}"
                )

        if not isinstance(result, dict):
            raise RuntimeError(
                "Gemma response must be a JSON object, "
                f"but received {type(result).__name__}."
            )

        return result