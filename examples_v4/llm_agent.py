from menglong import TaskAgent

from menglong.ml_model.schema.ml_request import UserMessage as user

agent = TaskAgent()

messages = [user(content="nihao")]

res = agent.chat(messages=messages)

print(res)
