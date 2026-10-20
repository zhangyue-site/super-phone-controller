"""Small fixed task router shared by text requests and cloud ASR."""
def script_for_text(text):
    return 'ui_agent.py' if '阿柴' in text else 'agent.py'

def select_task(body):
    if not isinstance(body,dict):raise ValueError('Task body must be an object')
    workflow=body.get('workflow')
    if workflow=='navigation-check':return {'script':'navigation.py','args':[],'result':'navigation-result.json','timeout':50}
    if workflow=='achai-read':return {'script':'ui_agent.py','args':[],'result':'achai-result.json','timeout':340}
    if workflow!='ai-task':raise ValueError('Unknown workflow')
    task=body.get('task')
    if not isinstance(task,str) or not 1<=len(task.strip())<=1000:raise ValueError('Invalid task')
    return {'script':script_for_text(task),'args':['--task',task],'result':'ai-task-result.json','timeout':340}
