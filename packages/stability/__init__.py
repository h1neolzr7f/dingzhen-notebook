"""P6 stability primitives: profiles, OCR corrections and local re-OCR."""

from .config import DeviceProfile, PageProfile, StabilityConfig
from .ocr_dictionary import ChoiceCorrection, OcrDictionary
from .region_recognition import RegionRecognition, recognize_region
from .timing import TimingSample, timed
from .update import UpdateManifest, download_update, fetch_update_manifest, update_available

__all__ = [
    "ChoiceCorrection",
    "DeviceProfile",
    "OcrDictionary",
    "PageProfile",
    "RegionRecognition",
    "StabilityConfig",
    "TimingSample",
    "recognize_region",
    "timed",
    "UpdateManifest",
    "download_update",
    "fetch_update_manifest",
    "update_available",
]
