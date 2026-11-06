def total(items):
    result = 0
    for item in items:
        result = result + item["price"] * item["qty"]
    return result


def average(values):
    return sum(values) / len(values)


def label(name):
    return "Item: " + name
