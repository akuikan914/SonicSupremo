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
    {"inputs": [], "name": "getNextPodId", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "getDashboardSnapshot", "outputs": [{"internalType": "uint256", "name": "totalFees", "type": "uint256"}, {"internalType": "uint256", "name": "totalDeposited", "type": "uint256"}, {"internalType": "uint256", "name": "totalWithdrawn", "type": "uint256"}, {"internalType": "uint256", "name": "totalRewardsPaid", "type": "uint256"}, {"internalType": "uint256", "name": "reserved", "type": "uint256"}, {"internalType": "uint256", "name": "contractBalance", "type": "uint256"}, {"internalType": "uint256", "name": "podCount", "type": "uint256"}, {"internalType": "bool", "name": "isPaused", "type": "bool"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "amountWei", "type": "uint256"}], "name": "quoteDeposit", "outputs": [{"internalType": "uint256", "name": "feeWei", "type": "uint256"}, {"internalType": "uint256", "name": "netWei", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}, {"internalType": "uint256", "name": "amountWei", "type": "uint256"}], "name": "simulateDeposit", "outputs": [{"internalType": "uint256", "name": "netWei", "type": "uint256"}, {"internalType": "uint256", "name": "unlockAt", "type": "uint256"}, {"internalType": "uint256", "name": "projectedRewardWei", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "fromId", "type": "uint256"}, {"internalType": "uint256", "name": "count", "type": "uint256"}], "name": "getPodsBatch", "outputs": [{"internalType": "uint256[]", "name": "ids", "type": "uint256[]"}, {"internalType": "uint256[]", "name": "lockSecondsArr", "type": "uint256[]"}, {"internalType": "uint256[]", "name": "rateBpsArr", "type": "uint256[]"}, {"internalType": "uint256[]", "name": "capWeiArr", "type": "uint256[]"}, {"internalType": "uint256[]", "name": "totalDepositedArr", "type": "uint256[]"}, {"internalType": "bool[]", "name": "activeArr", "type": "bool[]"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "address", "name": "user", "type": "address"}], "name": "getPodsWhereUserHasDeposits", "outputs": [{"internalType": "uint256[]", "name": "podIds", "type": "uint256[]"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}, {"internalType": "address", "name": "user", "type": "address"}], "name": "getDepositSummaryForUser", "outputs": [{"internalType": "uint256", "name": "totalPrincipal", "type": "uint256"}, {"internalType": "uint256", "name": "totalClaimableReward", "type": "uint256"}, {"internalType": "uint256", "name": "depositCount", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "protocolPaused", "outputs": [{"internalType": "bool", "name": "", "type": "bool"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "feeBps", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "BPS_DENOM", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "MAX_FEE_BPS", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "MIN_LOCK_SECONDS", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "MAX_LOCK_SECONDS", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "SECONDS_PER_YEAR", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}], "name": "getCapacityRemaining", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}, {"internalType": "address", "name": "user", "type": "address"}], "name": "getDepositIndicesUnlocked", "outputs": [{"internalType": "uint256[]", "name": "indices", "type": "uint256[]"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}, {"internalType": "address", "name": "user", "type": "address"}], "name": "getTotalWithdrawableForUserInPod", "outputs": [{"internalType": "uint256", "name": "totalPrincipal", "type": "uint256"}, {"internalType": "uint256", "name": "totalReward", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "getProtocolHealth", "outputs": [{"internalType": "bool", "name": "balanceOk", "type": "bool"}, {"internalType": "uint256", "name": "balanceWei", "type": "uint256"}, {"internalType": "uint256", "name": "reservedWei", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}, {"internalType": "uint256", "name": "amountWei", "type": "uint256"}], "name": "validateDepositParams", "outputs": [{"internalType": "bool", "name": "valid", "type": "bool"}, {"internalType": "string", "name": "err", "type": "string"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "getAvailablePodIds", "outputs": [{"internalType": "uint256[]", "name": "ids", "type": "uint256[]"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "address", "name": "user", "type": "address"}], "name": "getUserGlobalPrincipal", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "address", "name": "user", "type": "address"}], "name": "getUserGlobalClaimableReward", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
]

# -----------------------------------------------------------------------------
# Local reward calculation (mirrors contract formula)
# -----------------------------------------------------------------------------

BPS_DENOM_LOCAL = 10_000
SECONDS_PER_YEAR_LOCAL = 365 * 24 * 3600

def compute_reward_wei(principal_wei: int, rate_bps: int, elapsed_seconds: int, accrued_wei: int = 0) -> int:
    """Reward = principal * rateBps * elapsed / (BPS_DENOM * SECONDS_PER_YEAR) - accrued."""
    if principal_wei == 0 or elapsed_seconds <= 0:
        return 0
    full = (principal_wei * rate_bps * elapsed_seconds) // (BPS_DENOM_LOCAL * SECONDS_PER_YEAR_LOCAL)
    if full <= accrued_wei:
        return 0
    return full - accrued_wei

def compute_fee_wei(amount_wei: int, fee_bps: int) -> int:
    return (amount_wei * fee_bps) // BPS_DENOM_LOCAL

def compute_net_after_fee(amount_wei: int, fee_bps: int) -> int:
    return amount_wei - compute_fee_wei(amount_wei, fee_bps)

def project_reward_at_unlock(principal_wei: int, rate_bps: int, lock_seconds: int) -> int:
    """Projected reward if principal is locked for lock_seconds at rate_bps (full period)."""
    return (principal_wei * rate_bps * lock_seconds) // (BPS_DENOM_LOCAL * SECONDS_PER_YEAR_LOCAL)

def local_quote_deposit(amount_wei: int, fee_bps: int) -> Tuple[int, int]:
    """Local quote: (fee_wei, net_wei) for a deposit. Matches contract quoteDeposit."""
    fee = compute_fee_wei(amount_wei, fee_bps)
    return (fee, amount_wei - fee)

def local_simulate_deposit(amount_wei: int, fee_bps: int, lock_seconds: int, rate_bps: int) -> Tuple[int, int, int]:
    """Local simulation: (net_wei, projected_reward_wei). unlock_at not computed (needs block.timestamp)."""
    net = compute_net_after_fee(amount_wei, fee_bps)
    proj = project_reward_at_unlock(net, rate_bps, lock_seconds)
    return (net, proj, 0)

def check_capacity(contract, pod_id: int, amount_wei: int) -> bool:
    """Return True if pod has at least amount_wei capacity remaining."""
    try:
        rem = contract.functions.getCapacityRemaining(pod_id).call()
        return rem >= amount_wei
    except Exception:
        return False
