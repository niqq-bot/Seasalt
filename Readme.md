# Seasalt

**Turn your craving into an adventure.**

Seasalt is an AI-powered food adventure agent that transforms food cravings into personalized food journeys. Instead of simply recommending restaurants, it combines AI-generated suggestions with real restaurant and menu data to create food adventures based on a user's preferences, budget, and distance constraints.

Built with Python, Google's Gemma model, and Swiggy MCP, Seasalt connects natural-language food requests with real-world dining options.

## Overview

Finding something to eat can be overwhelming when there are too many options and no clear idea of what to choose.

Seasalt approaches this problem differently. Users describe what they are craving in natural language, optionally including their budget and preferred distance. The agent interprets the request, searches for nearby restaurants, retrieves available menu information, and generates a food adventure.

Python validation checks the generated selections against the retrieved restaurant and menu data before presenting the final adventure.

## Features

- **Natural-language craving interpretation:** Describe food preferences, flavors, dietary requirements, budget, and distance limits in plain English.
- **AI-powered adventure generation:** Use Gemma to generate personalized food adventures from the user's request.
- **Live restaurant discovery:** Search for restaurants through Swiggy MCP.
- **Menu retrieval:** Retrieve restaurant menu information to ground recommendations in actual menu data.
- **Budget validation:** Verify menu prices and ensure the final selected items remain within the specified budget.
- **Distance filtering:** Filter restaurants using verified distance information.
- **Restaurant validation:** Check restaurant identifiers and availability before including selections in the final adventure.
- **Terminal interface:** Interact with the application through a Python command-line interface.

## How It Works

Seasalt combines AI reasoning with external restaurant data and deterministic validation.

```text
User enters a food craving
          |
          v
Gemma interprets the request
          |
          v
Swiggy MCP searches restaurants
          |
          v
Restaurant menus are retrieved
          |
          v
Gemma generates a food adventure
          |
          v
Python validates the selections
          |
          v
The final adventure is displayed