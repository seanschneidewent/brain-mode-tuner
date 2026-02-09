# Learning Python with digestive examples 💩
# Progression from simple to complex

# === VERSION 1: Basic function ===
'''
def take_shit():
    print("pushing...")
    print("plop")
    print("done")

take_shit()
'''

# === VERSION 2: Functions with parameters + conditionals ===
'''
def take_shit(food):
    print("you ate " + food)
    print("pushing...")
    if food == "taco bell":
        print("EXPLOSIVE PLOP")
    else:
        print("plop")
    print("done")

take_shit("taco bell")
take_shit("salad")
'''

# === VERSION 3: Return values ===
'''
def take_shit(food):
    if food == "taco bell":
        return "explosive brown liquid"
    elif food == "salad":
        return "healthy green log"
    else:
        return "mystery plop"

result = take_shit("taco bell")
print("you produced: " + result)
'''

# === VERSION 4: Dictionaries as input and output ===
def take_shit(meal):
    print("digesting: " + meal["name"])
    if meal["spice_level"] == "fire":
        return {
            "consistency": "liquid",
            "color": "brown",
            "intensity": "explosive",
            "contains_corn": meal["had_corn"],
            "plop_count": 47
        }
    else:
        return {
            "consistency": "solid",
            "color": "green",
            "intensity": "easy",
            "plop_count": 1
        }

# Define meals as dictionaries
taco_bell = {
    "name": "taco bell feast",
    "items": ["crunchwrap supreme", "cheesy gordita crunch"],
    "spice_level": "fire",
    "had_corn": True
}

some_salad = {
    "name": "squirrel salad",
    "items": ["lettuce", "squirrel"],
    "spice_level": "nope",
    "had_corn": False
}

# === VERSION 5: Loops + accumulator pattern ===
def bathroom_session(meals):
    total_plops = 0
    for meal in meals:
        print("--- Processing: " + meal["name"] + " ---")
        result = take_shit(meal)
        total_plops = total_plops + result["plop_count"]
        print("Plops: " + str(result["plop_count"]))
    
    print("=== SESSION COMPLETE ===")
    print("Total plops: " + str(total_plops))
    return total_plops

# Run it
todays_meals = [taco_bell, some_salad]
bathroom_session(todays_meals)
