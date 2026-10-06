import json
import os
import re
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parent
USER_ROOT=Path('/Users/dzabrailovramzan')
SNAPSHOT=ROOT/'snapshot'
PROXY='http://127.0.0.1:43132'
MODELS={'codex':('gpt-6-astra','xhigh'),'claude':('claude-opus-5-5','max')}


def install(work,engine,arm):
    if arm=='A': return
    core=(SNAPSHOT/'core.md').read_text()
    if engine=='claude':
        (work/'CLAUDE.md').write_text(core)
        rule=work/'.claude/rules/kotlin.md';rule.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(SNAPSHOT/'rules/kotlin.md',rule)
        dest=work/'.claude/skills'
    else:
        # Kotlin rules have no native equivalent to Claude paths in this CLI adapter.
        # All pilot code tasks use this Kotlin/JVM project; preserve and disclose this load policy.
        rule=re.sub(r'\A---\n.*?\n---\n','',(SNAPSHOT/'rules/kotlin.md').read_text(),flags=re.S)
        (work/'AGENTS.md').write_text(core+'\n'+rule)
        dest=work/'.agents/skills'
    for folder in sorted((SNAPSHOT/'skills').glob('java-kotlin-*')):
        shutil.copytree(folder,dest/folder.name)


def child_env(engine,url):
    env=dict(os.environ)
    # Auth stays at its existing location. Do not override HOME or CODEX_HOME.
    for name in list(env):
        if name.startswith('CODEX_') and name not in ('CODEX_HOME',):
            env.pop(name,None)
        if name.startswith('CLAUDE_CODE_') or name in ('CLAUDE_SESSION_ID',):
            env.pop(name,None)
    env.update(HTTPS_PROXY=PROXY,HTTP_PROXY=PROXY,NO_PROXY='127.0.0.1,localhost')
    if engine=='claude':
        env.update(ANTHROPIC_BASE_URL=url,CLAUDE_CODE_DISABLE_AUTO_MEMORY='1',
                   CLAUDE_CODE_DISABLE_BACKGROUND_TASKS='1',CLAUDE_CODE_DISABLE_CRON='1')
    return env


def command(engine,work,arm,url):
    model,effort=MODELS[engine]
    if engine=='claude':
        settings={'enabledPlugins':{k:False for k in ['jkh@jkh','agents-md@builtin','telemetry@builtin','plugin-authoring@builtin']},
                  'autoMemoryEnabled':False,'disableBundledSkills':True,
                  'claudeMdExcludes':[str(USER_ROOT/'CLAUDE.md'),str(USER_ROOT/'AGENTS.md'),
                      str(USER_ROOT/'.claude/CLAUDE.md'),str(USER_ROOT/'.claude/rules/**'),
                      str(USER_ROOT/'IdeaProjects/**')],
                  'permissions':{'allow':['Read','Glob','Grep','Edit','Write','Bash'],'deny':['Agent','Task','WebFetch','WebSearch']}}
        overrides={}
        for folder in (USER_ROOT/'.claude/skills').glob('*'):
            if not folder.name.startswith('java-kotlin-'): overrides[folder.name]='off'
        settings['skillOverrides']=overrides
        if arm=='B':
            script=work/'.claude/hooks/ascii-punctuation.js';script.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(SNAPSHOT/'hooks/ascii-punctuation.js',script)
            # Same source hook with an explicit local path; no dependency on the live installation.
            settings['hooks']={'PostToolUse':[{'matcher':'Write|Edit','hooks':[{'type':'command','command':f'node {script}'}]}]}
        return ['claude','--setting-sources','project','--settings',json.dumps(settings),
                '--print','--model',model,'--effort',effort,'--tools','Read,Write,Edit,Glob,Grep,Bash,Skill',
                '--permission-mode','dontAsk','--strict-mcp-config','--mcp-config','{"mcpServers":{}}',
                '--no-session-persistence','--output-format','stream-json','--verbose','--include-hook-events']
    config=['model_reasoning_effort='+json.dumps(effort),'web_search="disabled"','developer_instructions=""',
            'project_doc_max_bytes='+('65536' if arm=='B' else '0'),
            'model_provider="pilot-http"','model_providers.pilot-http.name="Pilot HTTP"',
            'model_providers.pilot-http.base_url='+json.dumps(url+'/backend-api/codex'),
            'model_providers.pilot-http.requires_openai_auth=true',
            'model_providers.pilot-http.supports_websockets=false',
            'suppress_unstable_features_warning=true','approval_policy="never"',
            'sandbox_workspace_write.network_access=true','shell_environment_policy.inherit="core"',
            'shell_environment_policy.set.GRADLE_USER_HOME='+json.dumps(str(USER_ROOT/'.gradle'))]
    disabled=[]
    for base in [USER_ROOT/'.agents/skills',USER_ROOT/'.codex/skills']:
        for path in base.rglob('SKILL.md'):
            disabled.append('{path='+json.dumps(str(path.parent))+',enabled=false}')
        for p in base.glob('*/SKILL.md'):
            item='{path='+json.dumps(str(p.parent))+',enabled=false}'
            if item not in disabled:disabled.append(item)
    config.append('skills.config=['+','.join(disabled)+']')
    flags=[]
    for feature in ['plugins','memories','chronicle','hooks','multi_agent','multi_agent_v2','apps','skill_search',
                    'browser_use','computer_use','image_generation','goals','sleep_tool','workspace_dependencies',
                    'view_image','shell_snapshot','unbounded_connection_retries']:
        flags+=['--disable',feature]
    return ['codex','--no-daemon','exec','--ignore-user-config','--ignore-rules','--ephemeral',
            # A nested macOS sandbox cannot be installed inside sandbox-exec. The outer
            # profile provides the same experiment isolation for both client processes.
            '--skip-git-repo-check','-s','danger-full-access','-m',model,
            *sum((['-c',s] for s in config),[]),*flags,'--json','-C',str(work),'-']


def sandbox_profile(work):
    # Isolate fixtures and graders at the OS layer, while preserving existing client auth.
    denied=[str(USER_ROOT/'IdeaProjects'),str(USER_ROOT/'.local/share/code-reviews'),
            str(USER_ROOT/'.agents'),str(USER_ROOT/'.claude/skills'),str(USER_ROOT/'.claude/commands'),
            str(USER_ROOT/'.claude/rules'),str(USER_ROOT/'.claude/plugins'),
            str(USER_ROOT/'.codex/memories'),str(USER_ROOT/'.codex/plugins'),str(USER_ROOT/'.codex/skills')]
    literals=[str(USER_ROOT/'AGENTS.md'),str(USER_ROOT/'CLAUDE.md'),str(USER_ROOT/'.claude/CLAUDE.md'),
              str(USER_ROOT/'.codex/AGENTS.md')]
    rules=['(version 1)','(allow default)']
    # Preserve host projects and global Gradle configuration. Normal client state and
    # Gradle cache locks remain writable; immutable dependency artifacts do not.
    rules.append('(deny file-write* (subpath '+json.dumps(str(USER_ROOT))+'))')
    rules.append('(allow file-write* '+ ' '.join('(subpath '+json.dumps(str(USER_ROOT/p))+')' for p in ['.codex','.claude','.gradle'])+')')
    gradle_locked=[USER_ROOT/'.gradle/init.d',USER_ROOT/'.gradle/caches/modules-2/files-2.1']
    gradle_literals=[USER_ROOT/'.gradle/init.gradle',USER_ROOT/'.gradle/init.gradle.kts',USER_ROOT/'.gradle/gradle.properties']
    rules.append('(deny file-write* '+' '.join('(subpath '+json.dumps(str(p))+')' for p in gradle_locked)+' '+
                 ' '.join('(literal '+json.dumps(str(p))+')' for p in gradle_literals)+')')
    rules.append('(deny file-read-data file-write* '+ ' '.join('(subpath '+json.dumps(p)+')' for p in denied)+
                 ' '+' '.join('(literal '+json.dumps(p)+')' for p in literals)+')')
    rules.append('(deny file-read-data file-write* (require-all (regex #"^/private/tmp/jkh-") (require-not (subpath '+json.dumps(str(work))+'))))')
    return '\n'.join(rules)+'\n'
