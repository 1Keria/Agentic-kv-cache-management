"""Conservative online working-space reserve for real partial checkpoints.

The largest complete request seen so far supplies a Full workspace high water.
Only arrived request lengths are used, never the future trace. Protection is
capped at hard Full budget minus that workspace; this deliberately double
counts shared active/protected pages and is tested as a conservative ablation.
"""

from resizable_agent_budget import PoolTokens
from run_checkpoint_frontier import ObservedInputReplay


class WorkspaceInputReplay(ObservedInputReplay):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.workspace_high_water = 0
        self.original_protection_cap = self.controller.protection_cap

    def reserve_workspace(self, hard_full):
        cap = self.original_protection_cap
        self.controller.protection_cap = PoolTokens(
            min(cap.full, max(0, hard_full - self.workspace_high_water)), cap.swa)

    def update_budget(self, full, swa, version):
        self.reserve_workspace(full)
        receipt = super().update_budget(full, swa, version)
        receipt["workspace_high_water_full"] = self.workspace_high_water
        return receipt

    def request(self, row, index):
        working_set = (len(row["input_ids"]) + self.page_size - 1) // self.page_size * self.page_size
        self.workspace_high_water = max(self.workspace_high_water, working_set)
        self.reserve_workspace(self.controller.hard_budget.full)
        # Qualify with the new cap before the lookup/allocation, including any
        # genuine ancestor downgrade or physical-budget enforcement.
        self.controller._trim_protection()
        result = super().request(row, index)
        result["workspace_high_water_full"] = self.workspace_high_water
        result["workspace_protection_full_cap"] = self.controller.protection_cap.full
        return result
