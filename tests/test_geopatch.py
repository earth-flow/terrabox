"""
Minimal tests for the 'geopatch' toolkit using randomly generated inputs.

What this test does:
1) Injects an in-memory stub of the GeoPatch package if the real one is not available,
   so the test can run without external dependencies or data files.
2) Mocks a Registrar compatible with your platform's example.
3) Creates a random image tensor and a matching random label (segmentation mask).
4) Calls toolkit tools to validate the end-to-end workflow:
   - train_init (with numpy image/label)
   - train_info
   - generate_seg (npy, with returns)
   - generate_det (YOLO + optional segmentation)
   - visualize (no-op in stub; real package will plot)
   - pred_init (with another random image)
   - pred_save_tif / pred_save_npy (write small dummy outputs)

Run:
  python -m tests.test_geopatch
"""

import os
import sys
import types
import numpy as np

# ------------------------------------------------------------------------------
# 1) GeoPatch stub (comment out if you want to use the real GeoPatch package)
# ------------------------------------------------------------------------------
if "GeoPatch" not in sys.modules:
    gp_stub = types.ModuleType("GeoPatch")

    class TrainPatchStub:
        """
        A very small stub that accepts numpy arrays or paths (ignored),
        and writes simple outputs when asked to generate patches.
        """
        def __init__(self, image, label=None, patch_size=128, stride=128, channel_first=True,
                     shapefile_path=None, label_field=None):
            # Accept both numpy arrays and strings (paths)
            self.image = image
            self.label = label
            self.patch_size = patch_size
            self.stride = stride
            self.channel_first = channel_first
            self.shapefile_path = shapefile_path
            self.label_field = label_field

            # Basic sanity checks for numpy shape if arrays are provided
            if isinstance(image, np.ndarray):
                if channel_first:
                    assert image.ndim == 3 and image.shape[0] >= 1, \
                        "Expected image CHW when channel_first=True"
                else:
                    assert image.ndim == 3 and image.shape[2] >= 1, \
                        "Expected image HWC when channel_first=False"
            if isinstance(label, np.ndarray):
                assert label.ndim == 2, "Stub expects label as 2D segmentation mask (H, W)"

        def generate_segmentation(self, format="tif", folder_name="seg_patches", only_label=True,
                                  return_stacked=False, save_stack=False,
                                  V_flip=False, H_flip=False, Rotation=False):
            os.makedirs(folder_name, exist_ok=True)
            # For "npy": mimic returning stacked arrays when requested
            if format == "npy" and return_stacked:
                x_stack = np.zeros((4, 1, 32, 32), dtype=np.float32)  # dummy NHWC/NCWH is not relevant here
                y_stack = np.zeros((4, 32, 32), dtype=np.uint8)
                return (x_stack, y_stack)
            # For "tif": just create a dummy file to simulate work
            if format == "tif":
                with open(os.path.join(folder_name, "patch_000.tif"), "w") as f:
                    f.write("dummy")
            return None

        def generate_detection(self, format="npy", folder_name="det_patches", only_label=True,
                               return_stacked=False, save_stack=False,
                               V_flip=False, H_flip=False, Rotation=False,
                               segmentation=True):
            os.makedirs(folder_name, exist_ok=True)
            # Emit a YOLO-like label file to simulate detection output
            with open(os.path.join(folder_name, "000.txt"), "w") as f:
                f.write("0 0.5 0.5 0.2 0.2\n")
            if segmentation:
                with open(os.path.join(folder_name, "000_mask.npy"), "wb") as f:
                    np.save(f, np.zeros((32, 32), dtype=np.uint8))
            if format == "npy" and return_stacked:
                return (np.zeros((2, 1, 32, 32), dtype=np.float32),
                        np.zeros((2, 32, 32), dtype=np.uint8))
            return None

        def visualize(self, folder_name="seg_patches", patches_to_show=2, band_num=1,
                      fig_size=(10, 20), dpi=96, show_bboxes=False):
            # No-op in stub; ensure folder exists
            os.makedirs(folder_name, exist_ok=True)
            return

    class PredictionPatchStub:
        def __init__(self, image, patch_size=128, stride=128, channel_first=True):
            self.image = image
            self.patch_size = patch_size
            self.stride = stride
            self.channel_first = channel_first

        def save_Geotif(self, folder_name="pred_tif"):
            os.makedirs(folder_name, exist_ok=True)
            with open(os.path.join(folder_name, "tile_000.tif"), "w") as f:
                f.write("dummy")

        def save_numpy(self, folder_name="pred_npy"):
            os.makedirs(folder_name, exist_ok=True)
            with open(os.path.join(folder_name, "tile_000.npy"), "wb") as f:
                np.save(f, np.zeros((8, 8), dtype=np.float32))

    gp_stub.TrainPatch = TrainPatchStub
    gp_stub.PredictionPatch = PredictionPatchStub
    sys.modules["GeoPatch"] = gp_stub


# ------------------------------------------------------------------------------
# 2) Mock Registrar (compatible with your example)
# ------------------------------------------------------------------------------
class MockRegistrar:
    def __init__(self):
        self.toolkits = {}
        self.tools = {}
        self.handlers = {}

    def toolkit(self, name: str, description: str, version: str):
        self.toolkits[name] = {"description": description, "version": version}

    def tool(self, toolspec, handler):
        self.tools[toolspec.slug] = toolspec
        self.handlers[toolspec.slug] = handler

    def call(self, slug: str, arguments: dict, context: dict = None, account=None):
        if context is None:
            context = {}
        handler = self.handlers.get(slug)
        if not handler:
            raise KeyError(f"Tool not registered: {slug}")
        return handler(arguments, context, account)


# ------------------------------------------------------------------------------
# 3) Import toolkit (register tools) and run tests with random data
# ------------------------------------------------------------------------------
from src.terralink_platform.toolkits.geopatch import setup as geopatch_setup


def _rand_image_and_label(h=256, w=256, c=3, channel_first=True, n_classes=3):
    """
    Create a random image tensor and a matching random label (segmentation mask).
    - Image dtype: float32 in [0, 1]
    - Label dtype: uint8 in {0, 1, ..., n_classes-1}
    Shapes:
      CHW if channel_first, else HWC.
    """
    if channel_first:
        image = np.random.rand(c, h, w).astype(np.float32)
    else:
        image = np.random.rand(h, w, c).astype(np.float32)
    label = np.random.randint(0, n_classes, size=(h, w), dtype=np.uint8)
    return image, label


def main():
    reg = MockRegistrar()
    geopatch_setup(reg)

    # Generate a random image and label for training
    img, lbl = _rand_image_and_label(h=384, w=512, c=4, channel_first=True, n_classes=4)

    # 1) Train init (numpy inputs)
    out = reg.call("geopatch.train_init", {
        "image": img,            # numpy array (C,H,W)
        "label": lbl,            # numpy array (H,W) segmentation mask
        "patch_size": 128,
        "stride": 64,
        "channel_first": True
    }, context={"session_id": "rand_sess"})
    assert out["status"] == "initialized"
    print("train_init OK (numpy inputs)")

    # 2) Train info
    info = reg.call("geopatch.train_info", {}, context={"session_id": "rand_sess"})
    assert info["status"] == "ok"
    print("train_info OK")

    # 3) Generate segmentation patches (npy, with stacked returns)
    seg = reg.call("geopatch.generate_seg", {
        "format": "npy",
        "folder_name": "seg_npy_rand",
        "only_label": False,
        "return_stacked": True,
        "save_stack": False,
        "V_flip": True,
        "H_flip": True,
        "Rotation": True
    }, context={"session_id": "rand_sess"})
    assert seg["status"] == "done" and seg["returned_numpy"] is True
    print("generate_seg OK ->", seg["output_dir"])

    # 4) Generate detection patches (YOLO + optional segmentation)
    det = reg.call("geopatch.generate_det", {
        "format": "npy",
        "folder_name": "det_npy_rand",
        "only_label": True,
        "return_stacked": True,     # ask for returns in stub
        "segmentation": True
    }, context={"session_id": "rand_sess"})
    assert det["status"] == "done"
    print("generate_det OK ->", det["output_dir"])

    # 5) Visualize (no-op in stub; ensures folder exists)
    vis = reg.call("geopatch.visualize", {
        "folder_name": "seg_npy_rand",
        "patches_to_show": 2,
        "show_bboxes": True
    }, context={"session_id": "rand_sess"})
    assert vis["status"] == "rendered"
    print("visualize OK")

    # 6) Prediction init with another random image (no label needed)
    img2, _ = _rand_image_and_label(h=300, w=420, c=4, channel_first=True, n_classes=2)
    pinit = reg.call("geopatch.pred_init", {
        "image": img2,
        "patch_size": 128,
        "stride": 128,
        "channel_first": True
    }, context={"session_id": "rand_sess"})
    assert pinit["status"] == "initialized"
    print("pred_init OK")

    # 7) Prediction save (tif)
    ptif = reg.call("geopatch.pred_save_tif", {
        "folder_name": "pred_tif_rand"
    }, context={"session_id": "rand_sess"})
    assert ptif["status"] == "done" and os.path.isdir(ptif["output_dir"])
    print("pred_save_tif OK ->", ptif["output_dir"])

    # 8) Prediction save (npy)
    pnpy = reg.call("geopatch.pred_save_npy", {
        "folder_name": "pred_npy_rand"
    }, context={"session_id": "rand_sess"})
    assert pnpy["status"] == "done" and os.path.isdir(pnpy["output_dir"])
    print("pred_save_npy OK ->", pnpy["output_dir"])

    print("\nAll 'geopatch' random-input smoke tests passed.")


if __name__ == "__main__":
    main()
