from collections import namedtuple
from datetime import datetime, timedelta, timezone

from typing import List, Literal

import pytest

from brownie import OrderOfInk, reverts, web3, Wei

from eth_account.messages import encode_structured_data
from eth_abi.packed import encode_packed

import json


    # struct MintKey {
    #   address wallet;
    #   uint8 free;
    #   uint8 allowed;
    # }


def pack_choices(artists: List[Literal[1,2,3,4,5,6,7,8,9,10,11,12,13,14]], gold=False):
  return sum([1 << a for a in artists]) + int(gold)

def unpack_choices(packed: int):
  choices = []
  for i in range(1,15):
    if packed & 1 << i:
      choices.append(i)
  return (choices, bool(packed & 1))


def encode_mint_key(name, chainId, verifyingContract, wallet, free, allowed):
  msg = {
      "domain": {
          "name": name,
          "chainId": chainId,
          "version": '1',
          "verifyingContract": verifyingContract,
      },
      "message": {
          "wallet": wallet,
          "free": free,
          "allowed": allowed,
      },
      "primaryType": 'MintKey',
      "types": {
          "EIP712Domain": [
              {"name": 'name', "type": 'string'},
              {"name": 'version', "type": 'string'},
              {"name": 'chainId', "type": 'uint256'},
              {"name": 'verifyingContract', "type": 'address'},
          ],
          "MintKey": [
              {"name": 'wallet', 'type': 'address'},
              {"name": 'free', 'type': 'uint8'},
              {"name": 'allowed', 'type': 'uint8'},
          ]
      },
  }

  return encode_structured_data(primitive=msg)

def encode_combine_key(name, chainId, verifyingContract, tokenIds):
  msg = {
      "domain": {
          "name": name,
          "chainId": chainId,
          "version": '1',
          "verifyingContract": verifyingContract,
      },
      "message": {
          "tokenIds": tokenIds,
      },
      "primaryType": 'CombineKey',
      "types": {
          "EIP712Domain": [
              {"name": 'name', "type": 'string'},
              {"name": 'version', "type": 'string'},
              {"name": 'chainId', "type": 'uint256'},
              {"name": 'verifyingContract', "type": 'address'},
          ],
          "CombineKey": [
              {"name": 'tokenIds', 'type': 'uint256[]'},
          ]
      },
  }

  return encode_structured_data(primitive=msg)

class SignatureFactory:
  def __init__(self, signer, name="ORDEROFINK", chainId=1, verifyingContract=None):
    self.name = name
    self.chainId = chainId
    self.verifyingContract = verifyingContract
    self.signer = signer

  def sign_message(self, wallet="", free=0, allowed=0):
    msg = encode_mint_key(
      name=self.name,
      chainId=self.chainId,
      verifyingContract=self.verifyingContract,
      wallet=wallet,
      free=free,
      allowed=allowed,
      )
    signed_message = web3.eth.account.sign_message(msg, self.signer.private_key)
    return signed_message
  
  def sign_combine_message(self, tokenIds=[]):
    msg = encode_combine_key(
      name=self.name,
      chainId=self.chainId,
      verifyingContract=self.verifyingContract,
      tokenIds=tokenIds,
    )
    signed_message = web3.eth.account.sign_message(msg, self.signer.private_key)
    return signed_message
  
  def signature(self, wallet=None, free=0, allowed=0):
    return self.sign_message(wallet, free, allowed).signature

  def signature_combine(self, tokenIds=[]):
    return self.sign_combine_message(tokenIds).signature

 


@pytest.fixture
def signing_account(accounts):
  return accounts.add()


@pytest.fixture
def contract(accounts, signing_account):
  s = accounts[0].deploy(OrderOfInk, "ORDEROFINK", "INK", signing_account.address, accounts[0].address);
  return s


@pytest.mark.eip712
def test_signature(accounts, contract, signing_account):
  signer = SignatureFactory(verifyingContract=contract.address, signer=signing_account);
  signature = signer.signature(accounts[1].address, 0, 5)
  assert contract.autoclave(signature, (accounts[1].address, 0, 5), {"from": accounts[1]}) == True


@pytest.mark.mint
@pytest.mark.eip712
@pytest.mark.private
def test_allowlist_mints(accounts, contract, signing_account):
  signer = SignatureFactory(verifyingContract=contract.address, signer=signing_account);
  contract.pauseSwitch({"from": accounts[0]})
  # 100 Black Mints in Private Sale

  for i in range(1,11):
    signature = signer.signature(accounts[i].address, 0, 100)
    assert contract.autoclave(signature, (accounts[i].address, 0, 100), {"from": accounts[i]}) == True
    contract.getInked(
      signature,
      (accounts[i].address, 0, 100),
      100,
      0,
      pack_choices([i, i+1, i+2, i+3]),
      {"from": accounts[i], "value": 100 * Wei("0.08 ether")}
    )


@pytest.mark.mint
@pytest.mark.private
@pytest.mark.revert
def test_bad_mints(accounts, contract, signing_account):
  signer = SignatureFactory(verifyingContract=contract.address, signer=signing_account);
  contract.pauseSwitch({"from": accounts[0]})
  with reverts():
    for i in range(0,10):
      contract.getInked(
        signer.signature(accounts[i].address, 0, 10),
        (accounts[i].address, 0, 10),
        10,
        0,
        0,
        {"from": accounts[i], "value": (i+1) * 10 * Wei("0.0777 ether")}
      )


@pytest.mark.mint
@pytest.mark.revert
@pytest.mark.sellout
def test_out_of_mints(accounts, contract, signing_account):
  signer = SignatureFactory(verifyingContract=contract.address, signer=signing_account);
  contract.pauseSwitch({"from": accounts[0]})
  for i in range(1,23):
    contract.getInked(
      signer.signature(accounts[i].address, 0, 255),
      (accounts[i].address, 0, 255),
      192,
      0,
      0,
      {"from": accounts[i], "value": 192 * Wei("0.08 ether")}
    )
  for i in range(1,12):
    contract.getInked(
      signer.signature(accounts[i].address, 0, 255),
      (accounts[i].address, 0, 255),
      0,
      5,
      0,
      {"from": accounts[i], "value": 5 * Wei("0.4 ether")}
    )
  contract.getInked(
    signer.signature(accounts[12].address, 0, 255),
    (accounts[12].address, 0, 255),
    3,
    2,
    0,
    {"from": accounts[12], "value": 3 * Wei("0.08 ether") + 2 * Wei("0.4 ether")}
  )
  
  assert contract.totalSupply() == 4444
  
  with reverts():
    contract.getInked(
      signer.signature(accounts[2].address, 0, 255),
      (accounts[2].address, 0, 255),
      1,
      0,
      0,
      {"from": accounts[2], "value": Wei("0.08 ether")}
    )

@pytest.mark.mint
@pytest.mark.public
def test_public_mint(accounts, contract, signing_account):
  contract.pauseSwitch({"from": accounts[0]})

  with reverts():
    contract.getInked("", (accounts[1].address, 0, 1), 1, 0, 0, {"from": accounts[1], "value": Wei("0.123 ether")})

  assert contract.session() == 1
  contract.startNextSession({"from": accounts[0]})
  assert contract.session() == 2

  with reverts():
    contract.getInked("", (accounts[1].address, 0, 1), 1, 0, 0, {"from": accounts[1], "value": Wei("0.123 ether")})

  assert contract.session() == 2
  contract.startNextSession({"from": accounts[0]})
  assert contract.session() == 3

  
  contract.getInked("", (accounts[1].address, 0, 1), 1, 0, 0, {"from": accounts[1], "value": Wei("0.123 ether")})

  assert contract.session() == 3
  contract.startNextSession({"from": accounts[0]})
  assert contract.session() == 4

  with reverts():
    contract.getInked("", (accounts[1].address, 0, 1), 1, 0, 0, {"from": accounts[1], "value": Wei("0.08 ether")})

  contract.getInked("", (accounts[1].address, 0, 1), 1, 0, 0, {"from": accounts[1], "value": Wei("0.123 ether")})

@pytest.mark.mint
@pytest.mark.free
@pytest.mark.private
def test_free_mints(accounts, contract, signing_account):
  signer = SignatureFactory(verifyingContract=contract.address, signer=signing_account);
  contract.pauseSwitch({"from": accounts[0]})

  contract.getInked(
      signer.signature(accounts[1].address, 1, 3),
      (accounts[1].address, 1, 3), # 1 Free mint
      1,
      0,
      pack_choices([1,2,3,4,5]),
      {"from": accounts[1], "value": 1 * Wei("0.08 ether")}
    )
  
  assert contract.balanceOf(accounts[1].address) == 2
  # assert contract.explicitOwnershipOf(161)[3] == 0 # re-enable if free mints go to surprise-me
  assert contract.explicitOwnershipOf(162)[3] == pack_choices([1,2,3,4,5])

  contract.getInked(
      signer.signature(accounts[1].address, 1, 3),
      (accounts[1].address, 1, 3), # 1 Free mint
      0,
      1,
      pack_choices([6,7,8,9,10]),
      {"from": accounts[1], "value": 1 * Wei("0.4 ether")}
    )

  assert contract.balanceOf(accounts[1].address) == 3
  assert contract.explicitOwnershipOf(163)[3] == pack_choices([6,7,8,9,10], True)

  # One free mint (no paid)

  contract.getInked(
      signer.signature(accounts[2].address, 1, 3),
      (accounts[2].address, 1, 3), # 1 Free mint
      0,
      0,
      pack_choices([6,7,8,9,10]),
      {"from": accounts[2], "value": 0}
    )

  assert contract.balanceOf(accounts[2].address) == 1
  assert contract.explicitOwnershipOf(164)[3] == pack_choices([6,7,8,9,10])
  # assert contract.explicitOwnershipOf(164)[3] == 0 # re-enable if free mints go to surprise-me






def test_sellout_withdraw(accounts, contract, signing_account):
  signer = SignatureFactory(verifyingContract=contract.address, signer=signing_account);
  contract.pauseSwitch({"from": accounts[0]})
  
  for i in range(1,23):
    contract.getInked(
      signer.signature(accounts[i].address, 0, 255),
      (accounts[i].address, 0, 255),
      192,
      0,
      0,
      {"from": accounts[i], "value": 192 * Wei("0.08 ether")}
    )
  for i in range(1,12):
    contract.getInked(
      signer.signature(accounts[i].address, 0, 255),
      (accounts[i].address, 0, 255),
      0,
      5,
      0,
      {"from": accounts[i], "value": 5 * Wei("0.4 ether")}
    )
  contract.getInked(
    signer.signature(accounts[12].address, 0, 255),
    (accounts[12].address, 0, 255),
    3,
    2,
    0,
    {"from": accounts[12], "value": 3 * Wei("0.08 ether") + 2 * Wei("0.4 ether")}
  )
  
  expected_balance = 4227 * Wei("0.08 ether") + 57 * Wei("0.4 ether")
  
  assert contract.totalSupply() == 4444

  assert contract.balance() == expected_balance

  previous_balance = accounts[0].balance()

  contract.withdraw({"from": accounts[2], "value": 0})

  assert contract.balance() == 0

  assert accounts[0].balance() == previous_balance + expected_balance


def test_token_uri(accounts, contract, signing_account):
  signer = SignatureFactory(verifyingContract=contract.address, signer=signing_account);
  contract.pauseSwitch({"from": accounts[0]})
  
  for i in range(0,20):
    contract.getInked(
      signer.signature(accounts[i].address, 0, 255),
      (accounts[i].address, 0, 255),
      2,
      0,
      0,
      {"from": accounts[i], "value": 2 * Wei("0.08 ether")}
    )

  assert contract.tokenURI(1) == "https://theorderofink.com/api/1"

  contract.tattooReveal("https://forkhunger.art/", {"from": accounts[0]})

  with reverts():
    contract.tattooReveal("https://forkhungerr.art/", {"from": accounts[1]})

  assert contract.tokenURI(1) == "https://forkhunger.art/1"


@pytest.mark.choices
def test_choices(accounts, contract, signing_account):
  signer = SignatureFactory(verifyingContract=contract.address, signer=signing_account)
  contract.pauseSwitch({"from": accounts[0]})

  contract.getInked(
      signer.signature(accounts[1].address, 0, 255),
      (accounts[1].address, 0, 255),
      2,
      1,
      pack_choices([1,2,3,4,5]),
      {"from": accounts[1], "value": Wei("0.4 ether") + 2 * Wei("0.08 ether")}
    )
  
  assert contract.balanceOf(accounts[1]) == 3

  assert contract.explicitOwnershipOf(161)[3] == pack_choices([1,2,3,4,5])
  assert contract.explicitOwnershipOf(162)[3] == pack_choices([1,2,3,4,5])
  assert contract.explicitOwnershipOf(163)[3] == pack_choices([1,2,3,4,5], True)

  explicit_ownerships = contract.explicitOwnershipsOf([161,162,163])
  assert explicit_ownerships[0][3] == pack_choices([1,2,3,4,5])
  assert explicit_ownerships[1][3] == pack_choices([1,2,3,4,5])
  assert explicit_ownerships[2][3] == pack_choices([1,2,3,4,5], True)

  assert contract.explicitOwnershipsOfAll()[161][3] == pack_choices([1,2,3,4,5])
  assert contract.explicitOwnershipsOfAll()[162][3] == pack_choices([1,2,3,4,5])
  assert contract.explicitOwnershipsOfAll()[163][3] == pack_choices([1,2,3,4,5], True)

@pytest.mark.combine
def test_combines(accounts, contract, signing_account):
  signer = SignatureFactory(verifyingContract=contract.address, signer=signing_account)
  # break in interactive mode
  contract.pauseSwitch({"from": accounts[0]})

  contract.getInked(
    signer.signature(accounts[1].address, 0, 255),
    (accounts[1].address, 0, 255),
    192,
    0,
    0,
    {"from": accounts[1], "value": 192 * Wei("0.08 ether")}
  )
  
  assert contract.balanceOf(accounts[1].address) == 192

  with reverts():
    contract.finalSession(
    signer.signature_combine([161,162,163,164,165,166,167,168]),
    [161,162,163,164,165,166,167,168],
     {"from": accounts[2]})

  contract.finalSession(
    signer.signature_combine([161,162,163,164,165,166,167,168]),
    [161,162,163,164,165,166,167,168],
     {"from": accounts[1]})

  assert contract.balanceOf(accounts[1].address) == 185

  assert contract.ownerOf(353) == accounts[1].address

  assert contract.explicitOwnershipOf(161)[2] == True
  assert contract.explicitOwnershipOf(353)[3] == 1


@pytest.mark.eject
def test_eject(accounts, contract, signing_account):
  signer = SignatureFactory(verifyingContract=contract.address, signer=signing_account)
  contract.pauseSwitch({"from": accounts[0]})
  
  for i in range(1,23):
    contract.getInked(
      signer.signature(accounts[i].address, 0, 255),
      (accounts[i].address, 0, 255),
      100,
      0,
      0,
      {"from": accounts[i], "value": 100 * Wei("0.08 ether")}
    )
  for i in range(1,13):
    contract.getInked(
      signer.signature(accounts[i].address, 0, 255),
      (accounts[i].address, 0, 255),
      0,
      1,
      0,
      {"from": accounts[i], "value": 5 * Wei("0.4 ether")}
    )
  
  assert contract.blackRemaining() == 2027
  assert contract.goldRemaining() == 45

  contract.eject({"from": accounts[0]})

  assert contract.blackRemaining() == 1777
  assert contract.goldRemaining() == 0

  contract.eject({"from": accounts[0]})

  assert contract.blackRemaining() == 1527
  assert contract.goldRemaining() == 0

  contract.eject({"from": accounts[0]})

  assert contract.blackRemaining() == 1277
  assert contract.goldRemaining() == 0

  contract.eject({"from": accounts[0]})

  assert contract.blackRemaining() == 1027
  assert contract.goldRemaining() == 0

  contract.eject({"from": accounts[0]})

  assert contract.blackRemaining() == 777
  assert contract.goldRemaining() == 0

  contract.eject({"from": accounts[0]})

  assert contract.blackRemaining() == 527
  assert contract.goldRemaining() == 0

  contract.eject({"from": accounts[0]})

  assert contract.blackRemaining() == 277
  assert contract.goldRemaining() == 0

  contract.eject({"from": accounts[0]})

  assert contract.blackRemaining() == 27
  assert contract.goldRemaining() == 0

  contract.eject({"from": accounts[0]})
  
  assert contract.blackRemaining() == 0
  assert contract.goldRemaining() == 0





  







  