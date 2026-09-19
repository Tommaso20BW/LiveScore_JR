"""GitHub inspection and cleanup only. Deliberately no dispatch API."""
import os
import requests


class GitHub:
    def __init__(self, token, repository, session=None):
        if not token or not repository or '/' not in repository:
            raise RuntimeError('Configurazione GitHub mancante')
        self.base = f'https://api.github.com/repos/{repository}/'
        self.headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'}
        self.session = session or requests.Session()

    def request(self, method, path, **kwargs):
        try:
            r = self.session.request(method, self.base + path, headers=self.headers, timeout=15, **kwargs)
        except requests.RequestException:
            raise RuntimeError('GitHub non raggiungibile') from None
        return r

    def json(self, method, path, **kwargs):
        r = self.request(method, path, **kwargs)
        if r.status_code not in (200, 201, 204):
            raise RuntimeError(f'GitHub HTTP {r.status_code}')
        return r.json() if r.content else {}

    def runs(self, workflow):
        result = []
        for page in range(1, 101):
            batch = self.json('GET', f'actions/workflows/{workflow}/runs?per_page=100&page={page}')['workflow_runs']
            result.extend(batch)
            if len(batch) < 100:
                break
        return result

    def active_live_runs(self):
        return [str(r['id']) for r in self.runs('main_espn.yml')
                if r['status'] not in ('completed', 'queued', 'waiting', 'pending', 'requested')]

    def run_active(self, run_id, attempt=None):
        response = self.request('GET', f'actions/runs/{int(run_id)}')
        if response.status_code == 404:
            # A deleted run is not a running owner. First verify that the same
            # credential can actually read Actions in this repository; an
            # inaccessible repository must never release another process' lock.
            visible = self.json('GET', 'actions/runs?per_page=1')
            if not isinstance(visible.get('workflow_runs'), list):
                raise RuntimeError('Accesso Actions non verificato')
            return False
        if response.status_code != 200:
            raise RuntimeError(f'GitHub HTTP {response.status_code}')
        run = response.json()
        if attempt is not None and int(run['run_attempt']) > int(attempt):
            return False
        return run['status'] != 'completed'

    def delete(self, run_id):
        self.json('DELETE', f'actions/runs/{int(run_id)}')


def cleanup_completed(api, workflow_id, current_run_id):
    deleted = []
    for run in api.runs(workflow_id):
        if (run['status'] == 'completed' and str(run.get('workflow_id')) == str(workflow_id)
                and str(run['id']) != str(current_run_id)):
            api.delete(run['id'])
            deleted.append(run['id'])
    return deleted


def main():
    api = GitHub(os.environ['GH_TOKEN'], os.environ['GITHUB_REPOSITORY'])
    workflow_id = api.json('GET', 'actions/workflows/manual_graphics.yml')['id']
    deleted = cleanup_completed(api, workflow_id, os.environ['GITHUB_RUN_ID'])
    print(f'Pulizia generatore: {len(deleted)} run conclusi eliminati')


if __name__ == '__main__':
    main()
