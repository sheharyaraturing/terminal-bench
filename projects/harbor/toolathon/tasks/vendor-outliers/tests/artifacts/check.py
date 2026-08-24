"""The register exists and is laid out the way the format example fixes."""

import rewardkit as rk

rk.file_exists("exception_register.xlsx")
rk.register_columns()
rk.register_layout()
rk.register_unique()
rk.register_rounded()
