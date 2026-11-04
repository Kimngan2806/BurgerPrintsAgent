from contextvars import ContextVar

owner_context = ContextVar('owner', default='')
conversation_context = ContextVar('conversation', default='')
tool_events = ContextVar('tool_events', default=None)
