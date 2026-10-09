import json

from gemma import GemmaService


def main():

    gemma = GemmaService()

    user_input = (
        "I'm craving something spicy and crunchy, "
        "followed by something sweet. "
        "My budget is ₹500 and I have 2 hours."
    )

    print()
    print("=" * 50)
    print("          SEASALT + GEMMA")
    print("=" * 50)

    # --------------------------------------------------------
    # Step 1: Parse craving
    # --------------------------------------------------------

    print()
    print("Step 1: Parsing craving...")

    craving_profile = gemma.parse_craving(
        user_input
    )

    print(
        json.dumps(
            craving_profile,
            indent=4,
            ensure_ascii=False,
        )
    )

    # --------------------------------------------------------
    # Step 2: Prepare sample restaurant data
    # --------------------------------------------------------

    # Temporary test data only.
    # These are fictional examples, not real Swiggy results.

    sample_restaurants = [
        {
            "name": "Example Snack Restaurant",
            "restaurantId": "TEST001",
            "availabilityStatus": "OPEN",
            "distanceKm": 1.2,
            "menu": [
                {
                    "name": "Example Spicy Crunchy Snack",
                    "price": 120,
                    "isVeg": True,
                },
                {
                    "name": "Example Sweet Dessert",
                    "price": 90,
                    "isVeg": True,
                },
            ],
        },
        {
            "name": "Example Dessert Restaurant",
            "restaurantId": "TEST002",
            "availabilityStatus": "OPEN",
            "distanceKm": 2.0,
            "menu": [
                {
                    "name": "Example Chocolate Dessert",
                    "price": 150,
                    "isVeg": True,
                },
            ],
        },
    ]

    # --------------------------------------------------------
    # Step 3: Generate route plan
    # --------------------------------------------------------

    print()
    print("Step 2: Generating food adventure...")

    route_plan = gemma.generate_route_plan(
        craving_profile,
        sample_restaurants,
    )

    print()
    print("=" * 50)
    print("          SEASALT ROUTE PLAN")
    print("=" * 50)

    print(
        json.dumps(
            route_plan,
            indent=4,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()