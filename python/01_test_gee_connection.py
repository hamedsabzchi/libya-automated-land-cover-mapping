"""Earth Engine authentication and default-asset connectivity test."""

import os
import ee

PROJECT_ID = os.getenv("EE_PROJECT", "practical-proxy-441422-n6")
AOI_ASSET = "projects/practical-proxy-441422-n6/assets/Libya/Fezzan"
TRAINING_ASSET = "projects/practical-proxy-441422-n6/assets/Libya/TD-V4"


def main() -> None:
    ee.Authenticate(auth_mode="notebook", force=True)
    ee.Initialize(project=PROJECT_ID)
    aoi = ee.FeatureCollection(AOI_ASSET)
    training = ee.FeatureCollection(TRAINING_ASSET)
    print("SUCCESS: Earth Engine initialized.")
    print("AOI features:", aoi.size().getInfo())
    print("Training points:", training.size().getInfo())


if __name__ == "__main__":
    main()
