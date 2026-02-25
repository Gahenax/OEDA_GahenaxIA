import requests
import os
import json

def create_jira_issue_on_failure(audit_report_path: str, project_key: str = "OEDA"):
    """
    Agile Project Management Workflow:
    Cuando Gahenax falla en certificar un experimento matemático (System Auditor violado),
    automáticamente abre un ticket crtítico en Jira detallando la naturaleza del fallo,
    evitando que el humano tenga que triangular la caída de la infraestructura manualmente.
    """
    jira_url = os.environ.get("JIRA_API_URL", "https://oeda-observatory.atlassian.net/rest/api/3/issue")
    jira_email = os.environ.get("JIRA_EMAIL", "bot@oeda.network")
    jira_token = os.environ.get("JIRA_API_TOKEN", "")

    if not jira_token:
        print("[!] Token Agile no configurado. Saltando creación de issue automático.")
        return

    # Extraemos info del reporte de auditoría
    try:
        with open(audit_report_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            fail_reason = data.get("critical_failure_reason", "Desconocido")
            experiment = data.get("experiment", "Desconocido")
    except Exception:
        fail_reason = "Imposible leer reporte del auditor CMR."
        experiment = "N/A"

    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": f"[AUTOMATED CMR FAIL] Gahenax Core violation in {experiment}",
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": f"Gahenax Auditor reporta:\n\n{fail_reason}\n\nFavor revisar pipelines CI/CD."}
                        ]
                    }
                ]
            },
            "issuetype": {"name": "Bug"}
        }
    }

    try:
        res = requests.post(
            jira_url,
            json=payload,
            auth=(jira_email, jira_token),
            headers={"Accept": "application/json"}
        )
        if res.status_code == 201:
            issue_id = res.json().get("key")
            print(f"[+] Agile Workflow: Ticket subido exitosamente a Jira -> {issue_id}")
        else:
            print(f"[!] Error subiendo a Jira: {res.text}")
    except Exception as e:
        print(f"[!] Imposible conectar al board Agile: {e}")

if __name__ == "__main__":
    # Test
    # create_jira_issue_on_failure("reports/cmr_latest.json")
    pass
