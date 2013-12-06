import re
import common

smsg_types = ['slobb', 'stabl', 'sjoin', 'shand', 'strik', 'schat', 'swapw', 'swaps']
cmsg_types = ['cjoin','cchat','cplay','chand','cswap']

gen_msg_regex = '\[({0})(\|.*)*\]'.format('|'.join(cmsg_types + smsg_types))
msg_field_regex = '(?<=\|)[\w\ ]*(?=[\]\|])'

class PlayerStatus:
    # used to create player_stat objects that have the following fields:
    # PlayerStatus.status       -->     status of the player
    # PlayerStatus.strikes      -->     number of strikes the player has
    # PlayerStatus.name         -->     name server calls player's client
    # PlayerStatus.num_cards    -->     number of cards player has in hand

    def __init__(self):
        self.status = ''
        self.strikes = -1
        self.name = ''
        self.num_cards = -1

def split_buffer_into_msgs(buff):
    msgs = buff[1:-1].split('][')
    msgs = ['[' + msg + ']' for msg in msgs]
    return msgs 

def retrieve_msg_from_buff(buff):
    # returns msg, rest_of_buff
    if not buff:
        return None, buff

    assert(buff[0] == '[')
    end = buff.find(']')
    if end == -1:
        return None, buff

    return buff[0:end+1], buff[end+1:]

def str_to_cards(string):
    cards = string.split(',')
    cards = [int(card) for card in cards if int(card) != 52]
    return cards

def cards_to_str(cards, list_len):
    assert(list_len > 0)
    if not cards:
        return ','.join(['52' for i in range(list_len)])
    else:
        card_list = ','.join(['{0:02d}'.format(x) for x in cards])
        card_list += ',52' * (list_len - len(cards))
        return card_list

def hand_to_msg(hand):
    msg = '[shand|'
    msg += cards_to_str(hand, 18)
    msg += ']'
    return msg

def msg_to_hand(msg):
    assert(msg_type(msg) == 'shand')
    cardstr = fields(msg)[0]
    cards = cardstr.split(',')
    cards = [int(x) for x in cards]
    cards = [x for x in cards if x != 52]
    return cards

def is_valid(msg):
    return re.match(gen_msg_regex, msg)

def msg_type(msg):
    assert(msg)
    return msg[1:6]

def fields(msg):
    return msg[7:-1].split('|')

def lobby_to_slobb(lobby):
    msg = '[slobb|{0:02d}|{1}]'.format(len(lobby), ','.join(
        [player.name.ljust(8) for player in lobby]))
    return msg

def slobb_to_lobby(msg):
    lobby_str = msg[10:-1]
    lobby = lobby_str.split(',')
    lobby = [n.strip() for n in lobby]
    return lobby

def player_stat(player):
    if not player:
        return 'e0:        :00'
    ret = '{0}{1:01d}:{2:8}:{3:02d}'.format(player.status, player.strikes,
        player.name, len(player.hand))
    assert len(ret) == 14, "Invalid player_stat: {}".format(ret)
    return ret

def table_to_stabl(table):
    msg = '[stabl|'
    for player in table.players:
        msg += player_stat(player)
        msg += ','
    emptyseats = common.TABLESIZE - len(table.players)
    for i in range(emptyseats):
        msg += player_stat(None)
        msg += ','
    msg = msg[:-1] + '|'  # replace trailing comma
    msg += cards_to_str(table.last_play(), 4)
    if (table.starting_round):
        msg += '|1]'
    else:
        msg += '|0]'
    return msg

def stabl_to_player_stat_list(msg):
    assert(msg_type(msg) == 'stabl')
    player_stat_list = []
    for i in range(7,111,15):
        player_stat = PlayerStatus()
        player_stat.status = msg[i] 
        player_stat.strikes = int(msg[i+1])
        player_stat.name = msg[i+3:i+11].strip()
        player_stat.num_cards = int(msg[i+12:i+14])
        player_stat_list.append(player_stat)
    return player_stat_list

def stabl_to_last_play(msg):
    assert(msg_type(msg) == 'stabl')
    last_play = []
    cardstr = msg[112:123]
    cards = str_to_cards(cardstr)
    return cards


