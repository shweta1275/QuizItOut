import httpx

from app import config
from app.deploys import SHA_RE


class JenkinsError(Exception):
    pass


def trigger_rollback(sha: str, incident_id: int) -> None:
    """Start the rollback job. `sha` must come from the deploy table, never from user input."""
    s = config.settings
    if not SHA_RE.match(sha):
        raise JenkinsError("refusing to send a non-hex sha to Jenkins")
    if not (s.jenkins_user and s.jenkins_token):
        raise JenkinsError("JENKINS_USER / JENKINS_TOKEN are not set")
    try:
        r = httpx.post(
            f"{s.jenkins_url}/job/{s.jenkins_job}/buildWithParameters",
            params={"ROLLBACK_TO": sha, "INCIDENT_ID": str(incident_id)},
            auth=(s.jenkins_user, s.jenkins_token),
            timeout=15,
        )
    except httpx.HTTPError as e:
        raise JenkinsError(f"Jenkins unreachable: {e}") from e
    if r.status_code not in (200, 201):
        raise JenkinsError(f"Jenkins answered HTTP {r.status_code}")
