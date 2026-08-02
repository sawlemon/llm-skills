import { execFileSync } from 'node:child_process';

// npm runs prepare in CI and in regular clones. Configure hooks only when this
// directory is actually a Git worktree; package installation must remain safe
// in source archives and other non-Git environments.
try {
  execFileSync('git', ['rev-parse', '--git-dir'], { stdio: 'ignore' });
  execFileSync('git', ['config', 'core.hooksPath', '.githooks'], {
    stdio: 'ignore',
  });
} catch {
  // No Git worktree: nothing to configure.
}
