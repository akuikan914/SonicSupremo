#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SonicSupremo — CLI and client for the SonicSaver DeFi savings protocol.
Deposit ETH into pods, withdraw and claim rewards, list pods and user positions.
Guardian: register pods, set fee, pause/unpause.

SonicSaver is a time-bound savings protocol: users deposit ETH into "pods" with
a lock period and an APR (rate in basis points). After the lock expires, users
can withdraw principal plus accrued reward, or claim reward separately. A protocol
fee is taken at deposit and sent to the pulse collector. The guardian can register
pods, update caps/rates, set the fee, and pause the protocol.

Usage:
  python sonic_supremo_app.py config [--rpc-url URL] [--contract 0x...] [--save]
  python sonic_supremo_app.py deposit --rpc-url URL --private-key KEY --contract 0x... --pod-id N --amount-wei W
  python sonic_supremo_app.py withdraw --rpc-url URL --private-key KEY --contract 0x... --pod-id N --deposit-index I
  python sonic_supremo_app.py claim-reward --rpc-url URL --private-key KEY --contract 0x... --pod-id N --deposit-index I
  python sonic_supremo_app.py list-pods --rpc-url URL --contract 0x...
  python sonic_supremo_app.py user-deposits --rpc-url URL --contract 0x... --address 0x... [--pod-id N]
  python sonic_supremo_app.py protocol-stats --rpc-url URL --contract 0x...
  python sonic_supremo_app.py register-pod --rpc-url URL --private-key KEY --contract 0x... --lock-seconds S --rate-bps R --cap-wei C
  python sonic_supremo_app.py pause --rpc-url URL --private-key KEY --contract 0x...
  python sonic_supremo_app.py unpause --rpc-url URL --private-key KEY --contract 0x...
  python sonic_supremo_app.py quote --rpc-url URL --contract 0x... --amount-wei W
  python sonic_supremo_app.py simulate --rpc-url URL --contract 0x... --pod-id N --amount-wei W
  python sonic_supremo_app.py dashboard --rpc-url URL --contract 0x...
  python sonic_supremo_app.py version | constants | interactive | demo | summary | diagnostics

Config file: ~/.sonic_supremo/config.json (rpc_url, contract).
Environment: SONIC_SUPREMO_RPC_URL, SONIC_SUPREMO_CONTRACT override defaults.
Requires: web3 (pip install web3).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, List, Optional, Tuple

APP_NAME = "SonicSupremo"
APP_VERSION = "1.0.0"
CONTRACT_NAME = "SonicSaver"
CONFIG_DIR = ".sonic_supremo"
CONFIG_FILE = "config.json"
DEFAULT_RPC_URL = os.environ.get("SONIC_SUPREMO_RPC_URL", "http://127.0.0.1:8545")
DEFAULT_CONTRACT = os.environ.get("SONIC_SUPREMO_CONTRACT", "")

# Minimal ABI for SonicSaver (state-changing + view)
SONIC_SAVER_ABI = [
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}, {"internalType": "uint256", "name": "amountWei", "type": "uint256"}], "name": "deposit", "outputs": [], "stateMutability": "payable", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}, {"internalType": "uint256", "name": "depositIndex", "type": "uint256"}], "name": "withdraw", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}, {"internalType": "uint256", "name": "depositIndex", "type": "uint256"}], "name": "claimReward", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}, {"internalType": "uint256[]", "name": "depositIndices", "type": "uint256[]"}], "name": "withdrawBatch", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}, {"internalType": "uint256[]", "name": "depositIndices", "type": "uint256[]"}], "name": "claimRewardBatch", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "lockSeconds", "type": "uint256"}, {"internalType": "uint256", "name": "rateBps", "type": "uint256"}, {"internalType": "uint256", "name": "capWei", "type": "uint256"}], "name": "registerPod", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "newFeeBps", "type": "uint256"}], "name": "setFeeBps", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"internalType": "address", "name": "newGuardian", "type": "address"}], "name": "setGuardian", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [], "name": "pause", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [], "name": "unpause", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [], "name": "getProtocolStats", "outputs": [{"internalType": "uint256", "name": "totalFeesWei_", "type": "uint256"}, {"internalType": "uint256", "name": "totalDepositedWei_", "type": "uint256"}, {"internalType": "uint256", "name": "totalWithdrawnWei_", "type": "uint256"}, {"internalType": "uint256", "name": "totalRewardsPaidWei_", "type": "uint256"}, {"internalType": "uint256", "name": "reservedWei_", "type": "uint256"}, {"internalType": "uint256", "name": "podCount_", "type": "uint256"}, {"internalType": "bool", "name": "paused_", "type": "bool"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}], "name": "getPodInfo", "outputs": [{"internalType": "uint256", "name": "lockSeconds", "type": "uint256"}, {"internalType": "uint256", "name": "rateBps", "type": "uint256"}, {"internalType": "uint256", "name": "capWei", "type": "uint256"}, {"internalType": "uint256", "name": "totalDeposited", "type": "uint256"}, {"internalType": "bool", "name": "active", "type": "bool"}, {"internalType": "uint256", "name": "createdAtBlock", "type": "uint256"}, {"internalType": "bytes32", "name": "nameHash", "type": "bytes32"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}, {"internalType": "address", "name": "user", "type": "address"}], "name": "getUserDepositCount", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}, {"internalType": "address", "name": "user", "type": "address"}, {"internalType": "uint256", "name": "index", "type": "uint256"}], "name": "getUserDeposit", "outputs": [{"internalType": "uint256", "name": "principalWei", "type": "uint256"}, {"internalType": "uint256", "name": "unlockAt", "type": "uint256"}, {"internalType": "uint256", "name": "accruedRewardAtLock", "type": "uint256"}, {"internalType": "uint256", "name": "rateBpsAtDeposit", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}, {"internalType": "address", "name": "user", "type": "address"}, {"internalType": "uint256", "name": "depositIndex", "type": "uint256"}], "name": "getRewardForDeposit", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
