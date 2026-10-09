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
            api_key=api_key
        )

        self.model = "gemma-4-26b-a4b-it"

    # ========================================================
    # Parse user's craving
    # ========================================================

    def parse_craving(self, user_input: str) -> dict:

        prompt = f"""
You are the craving parser for Seasalt.

Seasalt transforms food cravings into personalized
food adventures.

Extract the user's preferences and return ONLY valid JSON.

Use this exact structure:

{{
    "craving": "short description",
    "flavors": [],
    "food_types": [],
    "dietary_preferences": [],
    "budget_inr": null,
    "time_minutes": null,
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
7. Default stops to 3 unless the user specifies
   a different number.
8. Never invent user preferences.
9. Return JSON only.

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
            "stops",
        }

        missing_fields = (
            required_fields - result.keys()
        )

        if missing_fields:
            raise RuntimeError(
                "Gemma craving profile is missing fields: "
                f"{missing_fields}"
            )

        return result

    # ========================================================
    # Generate personalized food route
    # ========================================================

    def generate_route_plan(
        self,
        craving_profile: dict,
        restaurant_data: list[dict],
    ) -> dict:
        """
        Generate a personalized food adventure from
        a craving profile and real Swiggy data.

        Gemma generates the plan but must not invent
        restaurants, dishes, prices, or distances.
        """

        if not restaurant_data:
            return {
                "title": "Your Seasalt Adventure",
                "summary": (
                    "We couldn't find enough restaurant "
                    "data to build your food adventure."
                ),
                "stops": [],
                "total_food_cost_inr": None,
                "remaining_budget_inr": None,
                "warnings": [
                    "No restaurant data was provided."
                ],
            }

        prompt = f"""
You are the food adventure planner for Seasalt.

Turn the user's craving into a personalized,
exciting food adventure.

The user wants a food adventure, not merely
a list of restaurant recommendations.

USER'S CRAVING PROFILE:
{json.dumps(craving_profile, ensure_ascii=False)}

REAL RESTAURANT AND MENU DATA FROM SWIGGY:
{json.dumps(restaurant_data, ensure_ascii=False)}

Return ONLY valid JSON using this structure:

{{
    "title": "short creative adventure title",
    "summary": "brief explanation of the adventure",
    "stops": [
        {{
            "stop_number": 1,
            "restaurant_name": "exact restaurant name",
            "restaurant_id": "exact restaurant ID",
            "dish_name": "exact dish name",
            "price_inr": 100,
            "distance_km": null,
            "reason": "why this dish matches the craving",
            "clue": "a fun clue for discovering this stop"
        }}
    ],
    "total_food_cost_inr": 300,
    "remaining_budget_inr": 200,
    "warnings": []
}}

RULES:

1. Use only restaurants and dishes present in
   the supplied Swiggy data.

2. Copy restaurant names, restaurant IDs, dish names,
   prices, and distances exactly from the supplied data.

3. Never invent restaurant names, dishes, prices,
   IDs, distances, opening hours, or travel times.

4. Recommend only restaurants whose
   availabilityStatus is OPEN.

5. Match dishes to the user's requested flavors,
   textures, food types, and dietary preferences
   wherever the data supports a match.

6. Respect the requested number of stops when
   sufficient suitable data is available.

7. Respect the user's total budget when prices
   are available. If the budget cannot be satisfied,
   explain the limitation in warnings.

8. Calculate total_food_cost_inr by adding the
   selected dish prices.

9. Calculate remaining_budget_inr only when the
   budget and every selected dish price are known.
   Otherwise return null.

10. Never claim a route is optimized or that the
    time limit is guaranteed.

11. If the supplied data is insufficient, return
    fewer stops and explain why in warnings.

12. Clues should be playful and should hint at the
    experience without inventing factual details.

13. Return JSON only. Do not include Markdown.
"""

        response = self._generate_with_retry(
            prompt=prompt,
            temperature=0.2,
        )

        result = self._parse_json_response(response)

        required_fields = {
            "title",
            "summary",
            "stops",
            "total_food_cost_inr",
            "remaining_budget_inr",
        }

        missing_fields = (
            required_fields - result.keys()
        )

        if missing_fields:
            raise RuntimeError(
                "Gemma route plan is missing fields: "
                f"{missing_fields}"
            )

        if not isinstance(result["stops"], list):
            raise RuntimeError(
                "Gemma route plan 'stops' must be a list."
            )

        return result

    # ========================================================
    # Generate content with retry handling
    # ========================================================

    def _generate_with_retry(
        self,
        prompt: str,
        temperature: float,
        max_attempts: int = 3,
    ):

        last_error = None

        for attempt in range(max_attempts):

            try:

                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=temperature,
                        response_mime_type="application/json",
                    ),
                )

                if not response.text:
                    raise RuntimeError(
                        "Gemma returned an empty response."
                    )

                return response

            except Exception as exc:

                last_error = exc

                print(
                    f"Gemma request failed "
                    f"({attempt + 1}/{max_attempts}): "
                    f"{exc}"
                )

                if attempt < max_attempts - 1:

                    delay = 2 ** (attempt + 1)

                    print(
                        f"Retrying in {delay} seconds..."
                    )

                    time.sleep(delay)

        raise RuntimeError(
            f"Gemma API request failed after "
            f"{max_attempts} attempts."
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

        # Handle JSON wrapped in Markdown code fences.
        if text.startswith("```"):

            lines = text.splitlines()

            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            text = "\n".join(lines).strip()

        # Parse JSON.
        try:

            result = json.loads(text)

        except json.JSONDecodeError as exc:

            raise RuntimeError(
                "Gemma returned invalid JSON:\n"
                f"{text}"
            ) from exc

        # We require an object, not an array or scalar.
        if not isinstance(result, dict):

            raise RuntimeError(
                "Gemma response must be a JSON object, "
                f"but received {type(result).__name__}.\n"
                f"Actual response:\n{text}"
            )

        return result