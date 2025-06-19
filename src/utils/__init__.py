# Utility modules for the daily profit model

# Silence repetitive pandas FutureWarnings coming from Woodwork
import warnings

# Only suppress the specific downcasting FutureWarning emitted by Woodwork logical_types
warnings.filterwarnings(
    "ignore",
    category=FutureWarning,
    module=r"woodwork\.logical_types",
)

# Silence Woodwork UserWarnings about date parsing fallback
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    module=r"woodwork\.type_sys\.utils",
)
