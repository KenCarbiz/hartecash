from fsbo.messaging.twilio_lookup import PhoneInfo, line_type_signal


def test_mobile_gives_positive_signal():
    info = PhoneInfo(phone="+18135551234", valid=True, line_type="mobile")
    assert line_type_signal(info) == 2


def test_landline_mild_positive():
    info = PhoneInfo(phone="+18135551234", valid=True, line_type="landline")
    assert line_type_signal(info) == 1


def test_voip_strong_penalty():
    info = PhoneInfo(phone="+18135551234", valid=True, line_type="voip")
    assert line_type_signal(info) == -8
    info2 = PhoneInfo(phone="+18135551234", valid=True, line_type="nonFixedVoip")
    assert line_type_signal(info2) == -8


def test_toll_free_penalty():
    info = PhoneInfo(phone="+18005551234", valid=True, line_type="toll-free")
    assert line_type_signal(info) == -5


def test_no_info_is_neutral():
    assert line_type_signal(None) == 0
    assert line_type_signal(PhoneInfo(phone="+1", valid=False)) == 0
    assert line_type_signal(PhoneInfo(phone="+1", valid=True, line_type=None)) == 0
