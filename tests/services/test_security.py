from app.security import hash_password, verify_password


def test_a_correct_password_verifies():
    assert verify_password("correct horse", hash_password("correct horse"))


def test_a_wrong_password_does_not():
    assert not verify_password("wrong", hash_password("correct horse"))


def test_the_same_password_hashes_differently_each_time():
    assert hash_password("same") != hash_password("same")


def test_malformed_hashes_never_match():
    assert not verify_password("x", "not-a-hash")
    assert not verify_password("x", "bcrypt$1$2$3$aa$bb")
    assert not verify_password("x", "scrypt$16384$8$1$zz$zz")
