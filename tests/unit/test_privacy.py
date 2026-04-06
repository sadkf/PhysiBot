"""Unit tests for integrations/privacy.py."""

from __future__ import annotations

from physi_core.integrations.privacy import PrivacyFilter


class TestPrivacyFilter:
    def test_keyword_detection(self) -> None:
        pf = PrivacyFilter(enabled=True, keywords=["密码", "password", "银行"])
        assert pf.contains_sensitive("我的密码是123") is True
        assert pf.contains_sensitive("password: abc") is True
        assert pf.contains_sensitive("你好世界") is False

    def test_bank_card_pattern(self) -> None:
        pf = PrivacyFilter(enabled=True)
        assert pf.contains_sensitive("卡号 6222021234567890123") is True
        assert pf.contains_sensitive("普通数字 123") is False

    def test_email_pattern(self) -> None:
        pf = PrivacyFilter(enabled=True)
        assert pf.contains_sensitive("邮箱 test@example.com") is True
        assert pf.contains_sensitive("没有邮箱") is False

    def test_pem_key_pattern(self) -> None:
        pf = PrivacyFilter(enabled=True)
        assert pf.contains_sensitive("-----BEGIN RSA KEY-----") is True

    def test_should_skip_app(self) -> None:
        pf = PrivacyFilter(ignore_apps=["KeePass", "1Password"])
        assert pf.should_skip_app("KeePass") is True
        assert pf.should_skip_app("keepass") is True
        assert pf.should_skip_app("VSCode") is False

    def test_redact_patterns(self) -> None:
        pf = PrivacyFilter(enabled=True)
        result = pf.redact("卡号 6222021234567890123")
        assert "[REDACTED]" in result
        assert "622202" not in result

    def test_redact_keyword_lines(self) -> None:
        pf = PrivacyFilter(enabled=True, keywords=["密码"])
        result = pf.redact("正常内容\n密码是abc123\n更多内容")
        assert "正常内容" in result
        assert "abc123" not in result
        assert "更多内容" in result

    def test_filter_frames_removes_sensitive(self) -> None:
        pf = PrivacyFilter(
            enabled=True,
            keywords=["secret"],
            ignore_apps=["KeePass"],
        )
        frames = [
            {"app_name": "VSCode", "text": "normal code"},
            {"app_name": "KeePass", "text": "credentials"},
            {"app_name": "Chrome", "text": "my secret data"},
            {"app_name": "Chrome", "text": "public page"},
        ]
        result = pf.filter_frames(frames)
        assert len(result) == 2
        assert result[0]["text"] == "normal code"
        assert result[1]["text"] == "public page"

    def test_disabled_privacy_passthrough(self) -> None:
        pf = PrivacyFilter(enabled=False, keywords=["password"])
        assert pf.contains_sensitive("password: abc") is False
        assert pf.redact("password: abc") == "password: abc"
