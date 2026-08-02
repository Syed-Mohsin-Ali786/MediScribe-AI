from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.medication_validation import validate_medications

@pytest.mark.asyncio
async def test_validate_medications_uses_fallback_when_rxnorm_unavailable() -> None:
    meds = [{"name": "acetaminophen", "dosage": "500 mg"}]
    with patch("app.services.medication_validation._rxnorm_lookup", return_value=None):
        result = await validate_medications(meds)

    assert result["source"] == "rxnorm_or_fallback"
    entry = result["medications"][0]
    assert entry["medication"]["name"] == "acetaminophen"
    # acetaminophen is seeded in the fallback JSON.
    assert entry["source"] == "fallback"
    assert entry["validated"] is True


@pytest.mark.asyncio
async def test_validate_medications_flags_unknown_drug() -> None:
    meds = [{"name": "totally-fake-drug-xyz", "dosage": "10 mg"}]
    with patch("app.services.medication_validation._rxnorm_lookup", return_value=None):
        result = await validate_medications(meds)

    assert result["all_valid"] is False
    entry = result["medications"][0]
    assert entry["source"] == "none"
    assert entry["validated"] is False


@pytest.mark.asyncio
async def test_validate_medications_missing_name() -> None:
    result = await validate_medications([{"dosage": "10 mg"}])
    assert result["all_valid"] is False
    assert result["medications"][0]["reason"] == "missing name"

