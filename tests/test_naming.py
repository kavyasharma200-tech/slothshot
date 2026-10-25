from slothshot.activities import _grounded, _slug


def test_slug_lowercases_and_joins_with_hyphens():
    assert _slug("Stripe Invoice: Failed Payment!") == "stripe-invoice-failed-payment"


def test_slug_drops_vague_words():
    assert _slug("screenshot of payment details") == "of-payment"


def test_slug_drops_repeats():
    assert _slug("paid-250-paid") == "paid-250"


def test_slug_keeps_seven_words_of_twenty_letters_at_most():
    slug = _slug("one two three four five six seven eight " + "x" * 30)
    assert slug == "one-two-three-four-five-six-seven"
    assert _slug("y" * 30) == "y" * 20


def test_slug_of_nothing_is_empty():
    assert _slug("") == ""
    assert _slug("Screenshot image") == ""


def test_grounded_counts_words_found_on_the_screenshot():
    text = "Payment successful\nPaid to Bhau's Chai Stall\nUPI ref 529814402217"
    assert _grounded("bhau-chai-stall-payment", text) == 4
    assert _grounded("lovely-sunset-photo", text) == 0


def test_grounded_matches_longer_words_inside_others():
    assert _grounded("npm-eresolve-dependency", "npm ERR! code ERESOLVE unable to resolve dependency tree") == 3
    # "postgres" is grounded by "PostgreSQL"
    assert _grounded("postgres-down", "PostgreSQL is down") == 2
    # but short words must match whole: "ab" is not grounded by "about"
    assert _grounded("ab-cd", "about cdrom") == 0
