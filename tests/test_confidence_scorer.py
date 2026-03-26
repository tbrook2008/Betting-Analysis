import pytest
from analysis.confidence_scorer import score, _normalize

def test_normalize_basic():
    # Test linear normalization for a known range (rolling_avg_7: 0.150 to 0.350)
    # 0.150 -> -1.0
    # 0.250 -> 0.0
    # 0.350 -> 1.0
    assert _normalize("rolling_avg_7", 0.150) == pytest.approx(-1.0)
    assert _normalize("rolling_avg_7", 0.250) == pytest.approx(0.0)
    assert _normalize("rolling_avg_7", 0.350) == pytest.approx(1.0)
    assert _normalize("rolling_avg_7", 0.100) == -1.0  # Clipped
    assert _normalize("rolling_avg_7", 0.400) == 1.0   # Clipped

def test_normalize_invert():
    # Test inverted normalization (xfip: 2.5 to 6.5, invert=True)
    # 2.5 -> 1.0 (good)
    # 4.5 -> 0.0
    # 6.5 -> -1.0 (bad)
    assert _normalize("xfip", 2.5) == 1.0
    assert _normalize("xfip", 4.5) == 0.0
    assert _normalize("xfip", 6.5) == -1.0

def test_score_hits_all_positive():
    signals = {
        "rolling_avg_7": 0.350,   # +1.0
        "rolling_avg_14": 0.350,  # +1.0
        "rolling_avg_30": 0.350,  # +1.0
        "handedness_split": 0.350, # +1.0
        "park_hit_factor": 1.20,   # +1.0
        "opp_pitcher_k_pct": 10.0, # +1.0 (inverted, low K% is good)
    }
    result = score(signals, "hits")
    assert result.recommendation == "OVER"
    assert result.confidence > 50
    assert any("✅" in r for r in result.reasoning)

def test_score_hits_all_negative():
    signals = {
        "rolling_avg_7": 0.150,   # -1.0
        "opp_pitcher_k_pct": 35.0, # -1.0 (inverted, high K% is bad)
    }
    result = score(signals, "hits")
    assert result.recommendation == "UNDER"
    assert result.confidence < 50
    assert any("❌" in r for r in result.reasoning)

def test_score_with_projection():
    # Signal-only score would be ~50 (neutral signals)
    signals = {"rolling_avg_7": 0.250} 
    # Projection is 2.0 while line is 1.0 (100% diff)
    # tanh(1.0 * 3.0) is ~0.995. Boost is ~0.995 * 50 = +49.75
    # Blend: 50 * 0.7 + (50 + 49.75) * 0.3 = 35 + 29.9 = 64.9
    result = score(signals, "hits", line=1.0, projected_value=2.0)
    assert result.confidence > 60
    assert "📈" in "".join(result.reasoning) or "📊" in "".join(result.reasoning)
