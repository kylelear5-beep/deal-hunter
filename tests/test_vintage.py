from niches import match_niches
import emailer, sitegen


def test_vintage_and_parts_match():
    d = {"store_domain": "ebay.com", "summary": "NOS carburetor for a classic truck", "discount_value": "20% off"}
    assert "vintage" in match_niches(d)
    assert "auto" in match_niches({"store_domain": "amazon.com", "summary": "Ceramic brake pads",
                                   "discount_value": "30% off"})
    assert match_niches({"store_domain": "amazon.com", "summary": "Vintage t-shirt", "discount_value": "30% off"}) == []


def test_vintage_in_email_and_signup():
    assert emailer.CATS["vintage"][0] == "DEALS_VINTAGE"
    assert 'value="vintage"' in sitegen.signup_box()
