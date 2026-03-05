
SAFETY_HARD_STOP_SIGNAL = 'SAFETY_HARD_STOP'

def check_persistence_policy(violation_count: int, threshold: int = 2) -> bool:
    """Legacy support function for persistence checking."""
    return violation_count >= threshold

class PRPEngine:
    def __init__(self):
        self.enforced_sessions = set()

    def should_hard_stop(self, violation_count: int, threshold: int = 2) -> bool:
        return violation_count >= threshold

    def evaluate_enforcement(self, session_id: str, ve_status: dict) -> dict:
        if ve_status['state'] == 'BREACH_LOCKED' and session_id not in self.enforced_sessions:
            self.enforced_sessions.add(session_id)
            return {
                'signal': SAFETY_HARD_STOP_SIGNAL,
                'actions': ['FLUSH_CONTEXT', 'TERMINATE_SESSION'],
                'authority': 'PRP',
                'status': 'AUTHORITY_HANDOVER',
                'termination_code': 'SAFETY_HARD_STOP',
                'enforcement_source': 'PRP_ENGINE',
                'authority_owner': 'PRP',
                'model_output_blocked': True
            }
        return {'signal': 'CONTINUE', 'actions': [], 'authority': 'MODEL'}

print('prp_engine.py updated with check_persistence_policy for backward compatibility.')
