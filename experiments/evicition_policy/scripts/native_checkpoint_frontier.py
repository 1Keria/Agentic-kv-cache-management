"""Real resident checkpoints with strictly read-only boundary discovery.

Unlike the initial v3 adapter, no artificial tail or input boundary is split.
An existing compressed node retains its actual Full/SWA dependency cost.
Missing endpoints or windows are rejected rather than materialized by policy.
"""

from checkpoint_frontier import CheckpointFrontier


class NativeCheckpointFrontier(CheckpointFrontier):
    def input_anchor(self, key, target):
        root = self.cache.root_node
        node, rest, depth = root, key[:target], 0
        while len(rest):
            child = node.children.get(rest.child_key(self.cache.page_size))
            if child is None or child.component_data[self.full_ct].value is None:
                return None
            count = child.key.match(rest, page_size=self.cache.page_size)
            if count <= 0 or count != len(child.key):
                return None
            depth += count
            node, rest = child, rest[count:]
        return node if depth == target and node is not root else None
