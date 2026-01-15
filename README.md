# Blackijecky – Networked Blackjack Game (Client/Server)

**Blackijecky** is a network-based **Blackjack** game implemented in Python using a **Client/Server** architecture.  
The server periodically broadcasts **UDP offer messages** that allow clients to automatically discover it on the local network, 
after which the actual gameplay is handled over a reliable **TCP connection**.

---

##  Features
- Automatic server discovery using **UDP Broadcast**
- Reliable game communication over **TCP**
- Shared protocol layer for message packing/unpacking
- Multi-client support on the server side (thread-based)
- Clean separation between Client, Server, and shared logic

---
