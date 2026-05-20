"""
CSAS API — Flask Blueprint for Cross-System Admissibility Score endpoints.

Routes:
    GET /api/csas/evaluations               — List all CSAS evaluations
    GET /api/csas/evaluation/<id>           — Get one evaluation with boundary scores
    GET /api/csas/grade/<upstream>/<downstream> — Latest CSAS grade for a model pair

Usage:
    from csas_api import csas_bp
    app.register_blueprint(csas_bp)
"""

import os
from flask import Blueprint, jsonify

import psycopg2
from psycopg2.extras import RealDictCursor

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
except ImportError:
    pass


csas_bp = Blueprint('csas', __name__)


# ============================================================================
# Database
# ============================================================================

def get_db():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg2.connect(url, cursor_factory=RealDictCursor)


# ============================================================================
# Grading scale (MTCP standard)
# ============================================================================

def csas_grade(score):
    """Assign MTCP letter grade to a CSAS score."""
    if score >= 0.90:
        return 'A'
    elif score >= 0.80:
        return 'B'
    elif score >= 0.70:
        return 'C'
    elif score >= 0.60:
        return 'D'
    else:
        return 'F'


# ============================================================================
# Routes
# ============================================================================

@csas_bp.route('/api/csas/evaluations', methods=['GET'])
def list_evaluations():
    """List all CSAS evaluations with summary scores."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                e.id,
                e.system_name,
                e.created_at,
                e.notes,
                s.bpr,
                s.cve,
                s.cir,
                s.caf,
                s.csas,
                s.grade,
                b.upstream_model,
                b.downstream_model,
                b.constraint_set
            FROM csas_evaluations e
            LEFT JOIN csas_scores s ON s.evaluation_id = e.id
            LEFT JOIN csas_boundaries b ON b.evaluation_id = e.id
            ORDER BY e.created_at DESC
        """)
        rows = cur.fetchall()

        evaluations = []
        for row in rows:
            evaluations.append({
                'id': row['id'],
                'system_name': row['system_name'],
                'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                'notes': row['notes'],
                'upstream_model': row['upstream_model'],
                'downstream_model': row['downstream_model'],
                'constraint_set': row['constraint_set'],
                'scores': {
                    'bpr': row['bpr'],
                    'cve': row['cve'],
                    'cir': row['cir'],
                    'caf': row['caf'],
                    'csas': row['csas'],
                    'grade': row['grade'],
                }
            })

        return jsonify({'evaluations': evaluations, 'count': len(evaluations)})
    finally:
        conn.close()


@csas_bp.route('/api/csas/evaluation/<int:evaluation_id>', methods=['GET'])
def get_evaluation(evaluation_id):
    """Get a single evaluation with all boundary scores and probe results."""
    conn = get_db()
    try:
        cur = conn.cursor()

        # Get evaluation
        cur.execute(
            "SELECT * FROM csas_evaluations WHERE id = %s",
            (evaluation_id,)
        )
        evaluation = cur.fetchone()
        if not evaluation:
            return jsonify({'error': 'Evaluation not found'}), 404

        # Get boundaries and scores
        cur.execute("""
            SELECT
                b.id AS boundary_id,
                b.upstream_model,
                b.downstream_model,
                b.constraint_set,
                s.bpr,
                s.cve,
                s.cir,
                s.caf,
                s.csas,
                s.grade
            FROM csas_boundaries b
            LEFT JOIN csas_scores s ON s.boundary_id = b.id
            WHERE b.evaluation_id = %s
        """, (evaluation_id,))
        boundaries = cur.fetchall()

        # Get probe results for each boundary
        boundary_data = []
        for b in boundaries:
            cur.execute("""
                SELECT probe_id, upstream_outcome, downstream_outcome,
                       upstream_ve, downstream_ve, cir_pass, created_at
                FROM csas_results
                WHERE boundary_id = %s
                ORDER BY probe_id
            """, (b['boundary_id'],))
            probe_results = cur.fetchall()

            boundary_data.append({
                'boundary_id': b['boundary_id'],
                'upstream_model': b['upstream_model'],
                'downstream_model': b['downstream_model'],
                'constraint_set': b['constraint_set'],
                'scores': {
                    'bpr': b['bpr'],
                    'cve': b['cve'],
                    'cir': b['cir'],
                    'caf': b['caf'],
                    'csas': b['csas'],
                    'grade': b['grade'],
                },
                'probe_results': [
                    {
                        'probe_id': r['probe_id'],
                        'upstream_outcome': r['upstream_outcome'],
                        'downstream_outcome': r['downstream_outcome'],
                        'upstream_ve': r['upstream_ve'],
                        'downstream_ve': r['downstream_ve'],
                        'cir_pass': r['cir_pass'],
                        'created_at': r['created_at'].isoformat() if r['created_at'] else None,
                    }
                    for r in probe_results
                ],
                'probe_count': len(probe_results),
            })

        return jsonify({
            'evaluation': {
                'id': evaluation['id'],
                'system_name': evaluation['system_name'],
                'created_at': evaluation['created_at'].isoformat() if evaluation['created_at'] else None,
                'notes': evaluation['notes'],
            },
            'boundaries': boundary_data,
        })
    finally:
        conn.close()


@csas_bp.route('/api/csas/grade/<path:upstream_model>/<path:downstream_model>', methods=['GET'])
def get_grade(upstream_model, downstream_model):
    """Get the latest CSAS grade for a specific model pair."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                s.bpr,
                s.cve,
                s.cir,
                s.caf,
                s.csas,
                s.grade,
                s.created_at,
                e.id AS evaluation_id,
                e.system_name,
                b.constraint_set
            FROM csas_scores s
            JOIN csas_boundaries b ON s.boundary_id = b.id
            JOIN csas_evaluations e ON s.evaluation_id = e.id
            WHERE b.upstream_model = %s
              AND b.downstream_model = %s
            ORDER BY s.created_at DESC
            LIMIT 1
        """, (upstream_model, downstream_model))
        row = cur.fetchone()

        if not row:
            return jsonify({
                'error': 'No CSAS evaluation found for this model pair',
                'upstream_model': upstream_model,
                'downstream_model': downstream_model,
            }), 404

        return jsonify({
            'upstream_model': upstream_model,
            'downstream_model': downstream_model,
            'evaluation_id': row['evaluation_id'],
            'system_name': row['system_name'],
            'constraint_set': row['constraint_set'],
            'scores': {
                'bpr': row['bpr'],
                'cve': row['cve'],
                'cir': row['cir'],
                'caf': row['caf'],
                'csas': row['csas'],
                'grade': row['grade'],
            },
            'evaluated_at': row['created_at'].isoformat() if row['created_at'] else None,
        })
    finally:
        conn.close()
