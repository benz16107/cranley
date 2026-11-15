"""Cranley on Photon 2.0: the same agent and tools, reached by iMessage, Telegram and a phone call.

client.py   the Photon API (send, attachments, typing, users and spaces)
state.py    one JSON file of threads: which workspace a chat is in, which message carried which answer
words.py    every line the agent sends, built from tool results (rule 5: no number comes from model text)
card.py     the picture of an answer: the plan with the result's findings and route, rendered by headless Chrome
speech.py   voice notes in (transcribed) and spoken answers out (an iMessage voice message)
router.py   one received message to one action
webhook.py  the only public piece: verifies Photon's signature and forwards to the private API
"""
