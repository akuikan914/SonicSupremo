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

def get_user_pod_ids(contract, user_address: str) -> List[int]:
    """Return list of pod ids where user has at least one deposit."""
    try:
        return list(contract.functions.getPodsWhereUserHasDeposits(user_address).call())
    except Exception:
        return []

def build_user_report_dict(contract, user_address: str) -> dict:
    """Build a dict with user's total principal, claimable reward, and per-pod breakdown."""
    pod_ids = get_user_pod_ids(contract, user_address)
    total_principal = 0
    total_claimable = 0
    pods = []
    for pid in pod_ids:
        princ, claimable, count = contract.functions.getDepositSummaryForUser(pid, user_address).call()
        total_principal += princ
        total_claimable += claimable
        pods.append({"pod_id": pid, "principal_wei": princ, "claimable_reward_wei": claimable, "deposit_count": count})
    return {
        "address": user_address,
        "total_principal_wei": total_principal,
        "total_claimable_reward_wei": total_claimable,
        "pods": pods,
    }

def format_user_report(report: dict) -> str:
    """Format build_user_report_dict output as multiline string."""
    lines = [
        f"Address: {report['address']}",
        f"Total principal: {format_wei(report['total_principal_wei'])}",
        f"Total claimable reward: {format_wei(report['total_claimable_reward_wei'])}",
        "Per-pod:",
    ]
    for p in report["pods"]:
        lines.append(f"  Pod #{p['pod_id']}: principal={format_wei(p['principal_wei'])}  claimable={format_wei(p['claimable_reward_wei'])}  deposits={p['deposit_count']}")
    return "\n".join(lines)

# -----------------------------------------------------------------------------
# Extended validation and eligibility helpers
# -----------------------------------------------------------------------------

def validate_pod_id_range(pod_id: int, next_pod_id: int) -> bool:
    """Return True if pod_id is in valid range [1, next_pod_id - 1]."""
    return 1 <= pod_id < next_pod_id

def validate_amount_positive(amount_wei: int) -> bool:
    return amount_wei > 0

def validate_fee_bps(fee_bps: int, max_fee_bps: int = 500) -> bool:
    return 0 <= fee_bps <= max_fee_bps

def validate_lock_seconds(lock_seconds: int, min_sec: int = 7 * 86400, max_sec: int = 730 * 86400) -> bool:
    return min_sec <= lock_seconds <= max_sec

def validate_rate_bps(rate_bps: int, max_rate_bps: int = 2000) -> bool:
    return 0 <= rate_bps <= max_rate_bps

def eligibility_deposit(contract, pod_id: int, amount_wei: int) -> Tuple[bool, str]:
    """Check if a deposit would be accepted. Returns (ok, message)."""
    try:
        valid, err = contract.functions.validateDepositParams(pod_id, amount_wei).call()
        if valid:
            return (True, "OK")
        return (False, err or "Unknown")
    except Exception as e:
        return (False, str(e))

def print_eligibility(contract, pod_id: int, amount_wei: int) -> None:
    """Print eligibility result for a deposit."""
    ok, msg = eligibility_deposit(contract, pod_id, amount_wei)
    if ok:
        print("Eligible: deposit would succeed (subject to sender balance and gas).")
    else:
        print("Not eligible:", msg)

# -----------------------------------------------------------------------------
# Command: check-eligibility
# -----------------------------------------------------------------------------

def cmd_check_eligibility(args: argparse.Namespace) -> int:
    rpc = args.rpc_url or load_config().get("rpc_url", DEFAULT_RPC_URL)
    contract_addr = args.contract or load_config().get("contract", DEFAULT_CONTRACT)
    pod_id = getattr(args, "pod_id", None)
    amount_wei = getattr(args, "amount_wei", None)
    if not contract_addr or pod_id is None or amount_wei is None:
        print("Error: --contract, --pod-id, --amount-wei required", file=sys.stderr)
        return 1
    try:
        pod_id = int(pod_id)
        amount_wei = parse_wei(str(amount_wei))
        w3 = get_w3(rpc)
        contract = get_contract(w3, contract_addr)
        print_eligibility(contract, pod_id, amount_wei)
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        return 1
    return 0

# -----------------------------------------------------------------------------
# Help-all: print all commands with one-line descriptions
# -----------------------------------------------------------------------------

COMMAND_HELP_ALL = """
config             Show or save RPC URL and contract address.
deposit            Deposit ETH into a pod (payable).
withdraw           Withdraw one deposit after unlock (principal + reward).
claim-reward       Claim reward for one unlocked deposit.
withdraw-batch     Withdraw multiple deposits in one transaction.
claim-reward-batch Claim rewards for multiple deposits.
list-pods          List all registered pods with lock, rate, cap, deposited.
user-deposits      List deposits for an address (optionally filter by pod).
user-global-stats  Total principal and claimable reward across all pods for an address.
user-report        Structured report for one address (principal, claimable, per-pod).
export-report      Export user report as JSON to a file.
protocol-stats     Protocol-level totals (fees, deposited, withdrawn, rewards, reserved).
protocol-health    Contract balance vs reserved (health check).
dashboard          Single-call snapshot: fees, deposited, withdrawn, reserved, balance, pods, paused.
summary            Dashboard + health + pods in one output.
available-pods     Pod IDs that are active and have capacity remaining.
pod-info           Detailed info for one pod (lock, rate, cap, deposited, active, created block).
validate-deposit   Check if deposit(podId, amountWei) would succeed.
check-eligibility  Alias-style check for deposit eligibility.
withdrawable       List withdrawable (unlocked) positions for an address.
register-pod       [Guardian] Register a new pod (lock seconds, rate bps, cap wei).
set-fee            [Guardian] Set protocol fee in basis points.
set-guardian       [Guardian] Set new guardian address.
pause              [Guardian] Pause protocol (no new deposits).
unpause            [Guardian] Unpause protocol.
quote              Quote fee and net principal for a deposit amount.
simulate           Simulate deposit: net principal, unlock time, projected reward.
gas-estimate       Estimate gas for deposit, withdraw, or claim-reward.
constants          Show contract constants (BPS_DENOM, MAX_FEE_BPS, lock limits, feeBps).
diagnostics        Run many view calls and print results (for support/debug).
demo               Print usage examples.
version            Show app version and contract name.
interactive        Print interactive mode hints.
"""

def cmd_help_all(args: argparse.Namespace) -> int:
    print("SonicSupremo commands:")
    print(COMMAND_HELP_ALL)
    return 0

# -----------------------------------------------------------------------------
# Contract events reference (for log parsing / indexers)
# -----------------------------------------------------------------------------

SONIC_SAVER_EVENTS = [
    "PodRegistered(podId,lockSeconds,rateBps,capWei)",
    "DepositPlaced(user,podId,amountWei,unlockAt)",
    "WithdrawalExecuted(user,podId,principalWei,rewardWei)",
    "RewardClaimed(user,podId,amountWei)",
    "FeeHarvested(collector,amountWei)",
    "GuardianSet(previousGuardian,newGuardian)",
    "ProtocolPaused(atBlock)",
    "ProtocolUnpaused(atBlock)",
    "PodCapUpdated(podId,previousCap,newCapWei)",
    "RateUpdated(podId,previousRateBps,newRateBps)",
    "EmergencySweep(tokenOrZero,amountWei)",
]

def get_contract_events_help() -> str:
    return "SonicSaver events:\n" + "\n".join("  " + e for e in SONIC_SAVER_EVENTS)

def cmd_events_help(args: argparse.Namespace) -> int:
    print(get_contract_events_help())
    return 0

# -----------------------------------------------------------------------------
# Default pod presets (for quick register-pod examples)
# -----------------------------------------------------------------------------

POD_PRESETS = {
    "30d_5pct_100eth": {"lock_seconds": 30 * 86400, "rate_bps": 500, "cap_wei": 100 * 10**18},
    "90d_7pct_500eth": {"lock_seconds": 90 * 86400, "rate_bps": 700, "cap_wei": 500 * 10**18},
    "180d_10pct_1000eth": {"lock_seconds": 180 * 86400, "rate_bps": 1000, "cap_wei": 1000 * 10**18},
    "365d_12pct_2000eth": {"lock_seconds": 365 * 86400, "rate_bps": 1200, "cap_wei": 2000 * 10**18},
}

def get_preset(name: str) -> Optional[dict]:
    return POD_PRESETS.get(name)

def cmd_presets(args: argparse.Namespace) -> int:
    print("Pod presets (for register-pod):")
    for name, p in POD_PRESETS.items():
        print(f"  {name}: lock={format_seconds(p['lock_seconds'])}  rate={format_bps(p['rate_bps'])}  cap={format_wei(p['cap_wei'])}")
    return 0

# -----------------------------------------------------------------------------
# Chain ID helper (for signing)
# -----------------------------------------------------------------------------

def get_chain_id(w3) -> int:
    try:
        return w3.eth.chain_id
    except Exception:
        return 0

def cmd_chain_id(args: argparse.Namespace) -> int:
    rpc = args.rpc_url or load_config().get("rpc_url", DEFAULT_RPC_URL)
    try:
        w3 = get_w3(rpc)
        cid = get_chain_id(w3)
        print("Chain ID:", cid)
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        return 1
    return 0

# -----------------------------------------------------------------------------
# Block number and timestamp (for unlock display)
# -----------------------------------------------------------------------------

def get_block_timestamp(w3, block_identifier: Any = "latest") -> int:
    try:
        block = w3.eth.get_block(block_identifier)
        return block["timestamp"]
    except Exception:
        return 0

def cmd_block_info(args: argparse.Namespace) -> int:
    rpc = args.rpc_url or load_config().get("rpc_url", DEFAULT_RPC_URL)
    try:
        w3 = get_w3(rpc)
        block = w3.eth.get_block("latest")
        print("Latest block:", block["number"], "timestamp:", block["timestamp"])
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        return 1
    return 0

# -----------------------------------------------------------------------------
# Full protocol snapshot (for export or audit)
# -----------------------------------------------------------------------------

def fetch_protocol_snapshot(contract) -> dict:
    """Fetch all protocol-level view data into a single dict. No user address needed."""
    stats = contract.functions.getProtocolStats().call()
    dash = contract.functions.getDashboardSnapshot().call()
    health = contract.functions.getProtocolHealth().call()
    next_id = contract.functions.getNextPodId().call()
    pods = []
    if next_id > 0:
        ids, lock_arr, rate_arr, cap_arr, dep_arr, active_arr = contract.functions.getPodsBatch(1, next_id - 1).call()
        for i in range(len(ids)):
            pods.append({
                "pod_id": ids[i],
                "lock_seconds": lock_arr[i],
                "rate_bps": rate_arr[i],
                "cap_wei": cap_arr[i],
                "total_deposited_wei": dep_arr[i],
                "active": active_arr[i],
            })
    return {
        "protocol_stats": {
            "total_fees_wei": stats[0],
            "total_deposited_wei": stats[1],
            "total_withdrawn_wei": stats[2],
            "total_rewards_paid_wei": stats[3],
            "reserved_wei": stats[4],
            "pod_count": stats[5],
            "paused": stats[6],
        },
        "dashboard": {
            "total_fees": dash[0],
            "total_deposited": dash[1],
            "total_withdrawn": dash[2],
            "total_rewards_paid": dash[3],
            "reserved": dash[4],
            "contract_balance": dash[5],
            "pod_count": dash[6],
            "is_paused": dash[7],
        },
        "health": {"balance_ok": health[0], "balance_wei": health[1], "reserved_wei": health[2]},
        "next_pod_id": next_id,
        "pods": pods,
    }

def cmd_protocol_snapshot(args: argparse.Namespace) -> int:
    """Print or export full protocol snapshot as JSON."""
    rpc = args.rpc_url or load_config().get("rpc_url", DEFAULT_RPC_URL)
    contract_addr = args.contract or load_config().get("contract", DEFAULT_CONTRACT)
    out_path = getattr(args, "output", None)
    if not contract_addr:
        print("Error: --contract or config required", file=sys.stderr)
        return 1
    try:
        w3 = get_w3(rpc)
        contract = get_contract(w3, contract_addr)
        snap = fetch_protocol_snapshot(contract)
        if out_path:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(snap, f, indent=2)
            print("Snapshot written to", out_path)
        else:
            print(json.dumps(snap, indent=2))
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        return 1
    return 0

# -----------------------------------------------------------------------------
# Utility: parse unlock timestamp for display
# -----------------------------------------------------------------------------

def format_unlock_time(unix_ts: int) -> str:
    if unix_ts <= 0:
        return "—"
    try:
        from datetime import datetime
        return datetime.utcfromtimestamp(unix_ts).isoformat() + "Z"
    except Exception:
        return str(unix_ts)

def format_unlock_relative(unix_ts: int, now_ts: Optional[int] = None) -> str:
    if unix_ts <= 0:
        return "—"
    if now_ts is None:
        now_ts = int(__import__("time").time())
    delta = unix_ts - now_ts
    if delta <= 0:
        return "unlocked"
    return "in " + format_seconds_long(delta)

# SonicSupremo targets SonicSaver contract; ensure contract address is set (config or --contract).
# For mainnet deployment use a verified RPC and the deployed SonicSaver address.
# Commands that modify state (deposit, withdraw, register-pod, pause, etc.) require --private-key.
# View-only commands (list-pods, dashboard, user-deposits, etc.) do not require a key.
# Use "python sonic_supremo_app.py demo" for usage examples and "help-all" for command list.
# Amounts are in wei unless stated; 1 ETH = 10^18 wei.

# -----------------------------------------------------------------------------
# Table / grid formatting helpers
# -----------------------------------------------------------------------------

def table_row(*cells: str, widths: Optional[List[int]] = None) -> str:
    if not widths:
        return "  ".join(cells)
    parts = []
    for i, c in enumerate(cells):
        w = widths[i] if i < len(widths) else len(c)
        parts.append(c.ljust(w))
    return "  ".join(parts)

def pad_eth(wei: int, width: int = 14) -> str:
    s = format_wei(wei)
    return s.rjust(width)

def pad_bps(bps: int, width: int = 8) -> str:
    s = format_bps(bps)
    return s.rjust(width)

# -----------------------------------------------------------------------------
# Full diagnostics: fetch and print many contract views (for support/debug)
# -----------------------------------------------------------------------------

def run_diagnostics(rpc_url: str, contract_addr: str) -> None:
    """Call multiple view functions and print results. No state change."""
    w3 = get_w3(rpc_url)
    contract = get_contract(w3, contract_addr)
    print("=== Protocol stats ===")
    total_fees, total_dep, total_wd, total_reward, reserved, pod_count, paused = contract.functions.getProtocolStats().call()
    print(f"  totalFees={format_wei(total_fees)}  totalDeposited={format_wei(total_dep)}  totalWithdrawn={format_wei(total_wd)}")
    print(f"  totalRewardPaid={format_wei(total_reward)}  reserved={format_wei(reserved)}  podCount={pod_count}  paused={paused}")
    print("=== Dashboard snapshot ===")
    t1, t2, t3, t4, res, bal, pc, pa = contract.functions.getDashboardSnapshot().call()
    print(f"  fees={format_wei(t1)}  deposited={format_wei(t2)}  withdrawn={format_wei(t3)}  rewards={format_wei(t4)}")
    print(f"  reserved={format_wei(res)}  balance={format_wei(bal)}  podCount={pc}  paused={pa}")
    print("=== Protocol health ===")
    ok, b, r = contract.functions.getProtocolHealth().call()
    print(f"  balanceOk={ok}  balance={format_wei(b)}  reserved={format_wei(r)}")
    print("=== Constants ===")
    bps = contract.functions.BPS_DENOM().call()
    max_fee = contract.functions.MAX_FEE_BPS().call()
    min_lock = contract.functions.MIN_LOCK_SECONDS().call()
    max_lock = contract.functions.MAX_LOCK_SECONDS().call()
    fee_bps = contract.functions.feeBps().call()
    print(f"  BPS_DENOM={bps}  MAX_FEE_BPS={max_fee}  MIN_LOCK={min_lock}  MAX_LOCK={max_lock}  feeBps={fee_bps}")
    next_id = contract.functions.getNextPodId().call()
    print(f"  nextPodId={next_id}")
    if next_id > 0:
        print("=== Pods (batch) ===")
        ids, lock_arr, rate_arr, cap_arr, dep_arr, active_arr = contract.functions.getPodsBatch(1, next_id - 1).call()
        for i in range(len(ids)):
            print(f"  {format_pod_line_short(ids[i], lock_arr[i], rate_arr[i], cap_arr[i], dep_arr[i], active_arr[i])}")
    print("=== Available pod IDs ===")
    avail = contract.functions.getAvailablePodIds().call()
    print(" ", avail)
    print("=== End diagnostics ===")

def cmd_diagnostics(args: argparse.Namespace) -> int:
    rpc = args.rpc_url or load_config().get("rpc_url", DEFAULT_RPC_URL)
    contract_addr = args.contract or load_config().get("contract", DEFAULT_CONTRACT)
    if not contract_addr:
        print("Error: --contract or config required", file=sys.stderr)
        return 1
    try:
        run_diagnostics(rpc, contract_addr)
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        return 1
    return 0

# -----------------------------------------------------------------------------
# Command: summary (dashboard + list-pods + health in one)
# -----------------------------------------------------------------------------

def cmd_summary(args: argparse.Namespace) -> int:
    rpc = args.rpc_url or load_config().get("rpc_url", DEFAULT_RPC_URL)
    contract_addr = args.contract or load_config().get("contract", DEFAULT_CONTRACT)
    if not contract_addr:
        print("Error: --contract or config required", file=sys.stderr)
        return 1
    try:
        w3 = get_w3(rpc)
        contract = get_contract(w3, contract_addr)
        print("--- Dashboard ---")
        t1, t2, t3, t4, res, bal, pc, pa = contract.functions.getDashboardSnapshot().call()
        print(f"Fees: {format_wei(t1)}  Deposited: {format_wei(t2)}  Withdrawn: {format_wei(t3)}  Rewards: {format_wei(t4)}")
        print(f"Reserved: {format_wei(res)}  Contract balance: {format_wei(bal)}  Pods: {pc}  Paused: {pa}")
        print("--- Health ---")
        ok, b, r = contract.functions.getProtocolHealth().call()
        print(f"Balance OK: {ok}  Balance: {format_wei(b)}  Reserved: {format_wei(r)}")
        next_id = contract.functions.getNextPodId().call()
        if next_id > 0:
            print("--- Pods ---")
            ids, lock_arr, rate_arr, cap_arr, dep_arr, active_arr = contract.functions.getPodsBatch(1, next_id - 1).call()
            for i in range(len(ids)):
                print(f"  {format_pod_line_short(ids[i], lock_arr[i], rate_arr[i], cap_arr[i], dep_arr[i], active_arr[i])}")
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        return 1
    return 0

# -----------------------------------------------------------------------------
# Command: user-report (structured report for one address)
# -----------------------------------------------------------------------------

def cmd_user_report(args: argparse.Namespace) -> int:
    rpc = args.rpc_url or load_config().get("rpc_url", DEFAULT_RPC_URL)
    contract_addr = args.contract or load_config().get("contract", DEFAULT_CONTRACT)
    address = getattr(args, "address", None)
    if not contract_addr or not address:
        print("Error: --contract and --address required", file=sys.stderr)
        return 1
    try:
        address = validate_address(address)
        w3 = get_w3(rpc)
        contract = get_contract(w3, contract_addr)
        report = build_user_report_dict(contract, address)
        print(format_user_report(report))
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        return 1
    return 0

# -----------------------------------------------------------------------------
# Command: export-report (write JSON to file)
# -----------------------------------------------------------------------------

def cmd_export_report(args: argparse.Namespace) -> int:
    rpc = args.rpc_url or load_config().get("rpc_url", DEFAULT_RPC_URL)
    contract_addr = args.contract or load_config().get("contract", DEFAULT_CONTRACT)
    address = getattr(args, "address", None)
    out_path = getattr(args, "output", None)
    if not contract_addr or not address or not out_path:
        print("Error: --contract, --address, --output required", file=sys.stderr)
        return 1
    try:
        address = validate_address(address)
        w3 = get_w3(rpc)
        contract = get_contract(w3, contract_addr)
        report = build_user_report_dict(contract, address)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print("Report written to", out_path)
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        return 1
    return 0

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------

def config_path() -> Path:
    return Path.home() / CONFIG_DIR / CONFIG_FILE

def load_config() -> dict:
    p = config_path()
    if not p.exists():
        return {"rpc_url": DEFAULT_RPC_URL, "contract": DEFAULT_CONTRACT}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"rpc_url": DEFAULT_RPC_URL, "contract": DEFAULT_CONTRACT}

def save_config(rpc_url: str, contract: str) -> None:
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"rpc_url": rpc_url, "contract": contract}, f, indent=2)

# -----------------------------------------------------------------------------
# Web3
# -----------------------------------------------------------------------------

def get_w3(rpc_url: str):
    try:
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not w3.is_connected():
            raise RuntimeError("Not connected to RPC")
        return w3
    except ImportError:
        raise RuntimeError("Install web3: pip install web3")

def get_contract(w3, address: str):
    from web3 import Web3
    return w3.eth.contract(address=Web3.to_checksum_address(address), abi=SONIC_SAVER_ABI)

def get_signer_account(w3, private_key: str):
    from web3 import Web3
    pk = private_key.strip()
    if pk.startswith("0x"):
        pk = pk[2:]
    return w3.eth.account.from_key(pk)

def normalize_address(addr: str) -> str:
    from web3 import Web3
    return Web3.to_checksum_address(addr)

# -----------------------------------------------------------------------------
# Formatting
# -----------------------------------------------------------------------------

def wei_to_ether(wei: int) -> float:
    return wei / 1e18

def ether_to_wei(eth: float) -> int:
    return int(eth * 1e18)

def format_wei(wei: int) -> str:
    return f"{wei_to_ether(wei):.6f} ETH"

def format_bps(bps: int) -> str:
    return f"{bps / 100:.2f}%"

def format_seconds(s: int) -> str:
    if s >= 86400 * 365:
        return f"{s // (86400 * 365)}y"
    if s >= 86400 * 30:
        return f"{s // (86400 * 30)}d"
    if s >= 86400:
        return f"{s // 86400}d"
    if s >= 3600:
        return f"{s // 3600}h"
    return f"{s}s"

# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------

def parse_wei(s: str) -> int:
    s = s.strip()
    if s.startswith("0x"):
        return int(s, 16)
    return int(s)

def validate_address(s: str) -> str:
    s = s.strip()
    if not s.startswith("0x"):
        s = "0x" + s
    if len(s) != 42:
        raise ValueError("Address must be 40 hex chars after 0x")
    return normalize_address(s)

def validate_pod_id(n: int) -> None:
    if n < 1:
        raise ValueError("pod_id must be >= 1")

# -----------------------------------------------------------------------------
# Commands: config
# -----------------------------------------------------------------------------

def cmd_config(args: argparse.Namespace) -> int:
    cfg = load_config()
    rpc = getattr(args, "rpc_url", None) or cfg.get("rpc_url", DEFAULT_RPC_URL)
    contract = getattr(args, "contract", None) or cfg.get("contract", DEFAULT_CONTRACT)
    print("RPC URL:", rpc)
    print("Contract:", contract or "(not set)")
    if getattr(args, "save", False):
        save_config(rpc, contract)
        print("Saved to", config_path())
    return 0

# -----------------------------------------------------------------------------
# Commands: deposit
# -----------------------------------------------------------------------------

def cmd_deposit(args: argparse.Namespace) -> int:
    rpc = args.rpc_url or load_config().get("rpc_url", DEFAULT_RPC_URL)
    contract_addr = args.contract or load_config().get("contract", DEFAULT_CONTRACT)
    if not contract_addr:
        print("Error: --contract or config required", file=sys.stderr)
        return 1
    pk = getattr(args, "private_key", None)
    if not pk:
        print("Error: --private-key required", file=sys.stderr)
        return 1
