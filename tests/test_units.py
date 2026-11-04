from watt_brief.units import DKK_PER_EUR, Display, convert_price, make_display


def test_eur_per_mwh_is_the_default_and_unchanged():
    assert convert_price(69.25) == 69.25


def test_mwh_to_kwh_divides_by_1000():
    assert convert_price(85.2, "kWh") == 0.0852


def test_dkk_per_mwh_multiplies_by_the_rate():
    assert convert_price(100.0, "MWh", 7.5) == 750.0


def test_dkk_per_kwh_combines_both():
    assert convert_price(100.0, "kWh", 7.5) == 0.75
    assert Display("kWh", "DKK", 7.5).convert(100.0) == 0.75


def test_negative_prices_convert_with_their_sign():
    assert convert_price(-20.0, "kWh", 7.5) == -0.15


def test_display_label():
    assert Display().label == "EUR/MWh"
    assert Display("kWh", "DKK", 7.5).label == "DKK/kWh"


def test_make_display_uses_the_fixed_krone_peg_and_leaves_eur_alone():
    assert make_display("MWh", "EUR") == Display()
    shown = make_display("kWh", "DKK")
    assert (shown.currency, shown.rate) == ("DKK", DKK_PER_EUR)
    assert shown.convert(100.0) == round(100.0 * 7.46038 / 1000, 6)


def test_the_peg_is_the_ermii_central_rate():
    assert DKK_PER_EUR == 7.46038
