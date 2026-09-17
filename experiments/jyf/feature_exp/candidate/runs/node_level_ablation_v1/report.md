# Node-level correlation and ablation

Samples used: 216874; duration: session-relative next demand time; node-level persistent prefix; no eviction.

## Main models
- full18: IBS=0.23005; AUC@1/2/4tau=0.7047/0.7711/0.7875
- old10: IBS=0.27730; AUC@1/2/4tau=0.5651/0.6782/0.7224
- candidate8: IBS=0.33547; AUC@1/2/4tau=0.5275/0.5153/0.5078

## Group/leave-one-out ablation
|set|IBS|AUC@1|AUC@2|AUC@4|
|-|-|-|-|-|
|without_old_structure|0.26135|0.6799|0.6388|0.6454|
|without_old_node_time|0.26312|0.6920|0.8086|0.7946|
|without_old_history|0.23007|0.7107|0.8168|0.8197|
|without_old_workload|0.26539|0.6961|0.6823|0.6933|
|without_candidate_context|0.27688|0.6708|0.6378|0.6634|
|without_candidate_history|0.27573|0.5791|0.7497|0.7804|
|without_candidate_position|0.26399|0.6926|0.6835|0.6902|
|without_node_tokens|0.25560|0.7040|0.6890|0.6871|
|without_path_tokens|0.24349|0.7317|0.6887|0.6890|
|without_age_seconds|0.24609|0.7321|0.7469|0.7423|
|without_idle_seconds|0.24698|0.7121|0.7716|0.7811|
|without_hits|0.26956|0.6517|0.6581|0.6755|
|without_gap_present|0.23948|0.7585|0.7654|0.7602|
|without_recent_gap_seconds|0.26718|0.6562|0.6988|0.6970|
|without_gap_ewma_seconds|0.26970|0.6564|0.6510|0.6563|
|without_gap_std_seconds|0.23674|0.7509|0.7879|0.7669|
|without_is_agent|0.26539|0.6961|0.6823|0.6933|
|without_creation_turn_fraction|0.26399|0.6926|0.6835|0.6902|
|without_endpoint_is_tool|0.26455|0.6901|0.6698|0.6837|
|without_tool_schema_count|0.23686|0.7264|0.7529|0.7640|
|without_last_message_is_tool|0.25970|0.6881|0.6714|0.6866|
|without_last_message_is_user|0.25303|0.7100|0.7323|0.7447|
|without_prefix_gap_ewma_rel|0.26927|0.6717|0.6851|0.7035|
|without_prefix_reuse_rate8|0.27049|0.6602|0.6454|0.6587|
|without_prefix_turn_gap_last|0.25581|0.5996|0.7527|0.7839|