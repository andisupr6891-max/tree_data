"""gcquant — mesin hitung & analisis pribadi untuk emas COMEX (GC/MGC/OG) dan XAUUSD.

Sumber data utama: Databento GLBX.MDP3 (MBO, MBP-10, trades, statistics, definition).
Pengaman biaya aktif secara bawaan: tidak ada unduhan berbayar tanpa izin eksplisit.
"""
from .core import (
    SPECS, DEFAULT_COSTS, ContractSpec, CostModel,
    BiayaDitolak, GcquantError, LookAheadError,
)

__version__ = "0.1.0"

__all__ = [
    "SPECS", "DEFAULT_COSTS", "ContractSpec", "CostModel",
    "BiayaDitolak", "GcquantError", "LookAheadError", "__version__",
]
