class ViolationState:
    BASELINE = 'BASELINE'
    CORRECTION_PENDING = 'CORRECTION_PENDING'
    BREACH_LOCKED = 'BREACH_LOCKED'

class ViolationEngine:
    def __init__(self, threshold=2):
        self.threshold = threshold
        self.sessions = {}
        self.counts = {} # Simple count for legacy update_and_get support

    def reset(self, probe_id: str):
        """Clears data for a given ID to restart tracking."""
        if probe_id in self.sessions:
            del self.sessions[probe_id]
        self.counts[probe_id] = 0

    def update_and_get(self, probe_id: str) -> int:
        """Increments the violation count for a given probe_id and returns the new count."""
        self.counts[probe_id] = self.counts.get(probe_id, 0) + 1
        return self.counts[probe_id]

    def handle_event(self, session_id, event_type):
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                'state': ViolationState.BASELINE,
                'current_score': 0,
                'previous_score': 0,
                'consecutive_violation_count': 0
            }

        s = self.sessions[session_id]
        s['previous_score'] = s['current_score']

        if event_type == 'USER_CORRECTION':
            s['state'] = ViolationState.CORRECTION_PENDING
        elif event_type == 'CONSTRAINT_VIOLATED':
            if s['state'] == ViolationState.CORRECTION_PENDING:
                s['current_score'] += 1
                s['consecutive_violation_count'] += 1
                if s['current_score'] >= self.threshold:
                    s['state'] = ViolationState.BREACH_LOCKED
        elif event_type == 'CONSTRAINT_PASSED':
            s['state'] = ViolationState.BASELINE
            s['current_score'] = 0
            s['consecutive_violation_count'] = 0
        return s

print('ve_engine.py updated with update_and_get and reset methods.')
