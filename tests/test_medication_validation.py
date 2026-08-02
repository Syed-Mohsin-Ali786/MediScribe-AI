from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.medication_validation import validate_medications

@pytest.mark.asyncio
async def test_validate_medications_uses_fallback_when_rxnorm_unavailable() -> None:
    meds = [{"name": "acetaminophen", "dosage": "500 mg"}]
    with patch("app.services.medication_validation._rxnorm_lookup", return_value=None):
        result = await validate_medications(meds)

    assert len(result) == 1
    entry = result[0]
    assert entry["medication"] == "acetaminophen"
    # acetaminophen is seeded in the fallback JSON.
    assert entry["status"] == "valid"


@pytest.mark.asyncio
async def test_validate_medications_flags_unknown_drug() -> None:
    meds = [{"name": "totally-fake-drug-xyz", "dosage": "10 mg"}]
    with patch("app.services.medication_validation._rxnorm_lookup", return_value=None):
        result = await validate_medications(meds)

    assert len(result) == 1
    entry = result[0]
    assert entry["status"] == "unrecognized"
    assert entry["medication"] == "totally-fake-drug-xyz"


@pytest.mark.asyncio
async def test_validate_medications_missing_name() -> None:
    result = await validate_medications([{"dosage": "10 mg"}])
    assert len(result) == 1
    assert result[0]["status"] == "unrecognized"
    assert "Missing medication name" in result[0]["note"]

