import json

with open('.campaign_state.json', 'r') as f:
    state = json.load(f)

state['status'] = 'idle'
state['resume_point'] = 0
state['failed_this_run'] = 0
state['sent'] = 0
state['failed'] = 0
state['sent_this_run'] = 0
state['processed_this_run'] = 0
state['last_row_index'] = 0
state['emails_failed'] = 0
state['total_rows_in_file'] = 29
state['total'] = 29

with open('.campaign_state.json', 'w') as f:
    json.dump(state, f, indent=2)

print("Updated .campaign_state.json successfully.")
