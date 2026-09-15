"""Minimal Earth Engine authentication/initialization test for Google Colab."""

import ee

PROJECT_ID = "practical-proxy-441422-n6"


def main() -> None:
    ee.Authenticate(auth_mode="notebook", force=True)
    ee.Initialize(project=PROJECT_ID)
    print("SUCCESS: Earth Engine initialized.")


if __name__ == "__main__":
    main()
