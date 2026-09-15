"""Require a dated, complete ingredient-label review; never infer origin from titles."""
from datetime import date


def approved(product, reviews, today=None):
    today = today or date.today()
    review = reviews.get(str(product.get("productId")), {})
    try:
        age = (today - date.fromisoformat(review["checked_on"])).days
        ingredients = review["ingredients"]
        return (
            review.get("status") == "approved"
            and review.get("product_name") == product.get("productName")
            and bool(review.get("reviewer", "").strip())
            and review.get("complete_ingredient_list") is True
            and review.get("all_subingredients_checked") is True
            and review.get("same_options_and_origin") is True
            and 0 <= age <= 30
            and review.get("source_url", "").startswith("https://")
            and bool(review.get("label_evidence", "").strip())
            and isinstance(ingredients, list) and bool(ingredients)
            and all(isinstance(i, dict) and i.get("name")
                    and i.get("origin") == "대한민국"
                    and i.get("evidence") for i in ingredients)
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return False
