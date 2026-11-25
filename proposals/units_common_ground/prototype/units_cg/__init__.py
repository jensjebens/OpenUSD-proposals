"""Prototype of the units common-ground proposal. Requires the codeless schema plugin in
../plugin/resources on PXR_PLUGINPATH_NAME; `import units_cg` sets that up if missing."""
import os

_PLUGIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "plugin", "resources")
if _PLUGIN not in os.environ.get("PXR_PLUGINPATH_NAME", ""):
    os.environ["PXR_PLUGINPATH_NAME"] = os.pathsep.join(
        p for p in (_PLUGIN, os.environ.get("PXR_PLUGINPATH_NAME")) if p)

from .author import apply_units, author_from_source, compensate_spatial  # noqa: E402
from .convert import SI, MissingDimension, read_in  # noqa: E402
from .dimensions import get_dimension  # noqa: E402
from .resolve import compute_effective, unit_system  # noqa: E402
from .validators import validate  # noqa: E402
