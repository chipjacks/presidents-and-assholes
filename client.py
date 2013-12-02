import common
import message
import logging
import clientgui
import socket
import getopt
import sys
import time
from multiprocessing.pool import ThreadPool

def current_turn_num(player_stat_list):
    assert(player_stat_list)
    for i, player_stat in enumerate(player_stat_list):
        if player_stat.status == 'a':
            return i
    else:
        # game could be over
        logging.info('Server sent stabl with no one active.')
        return -1

class Client():
    def __init__(self, name, auto=True):
        self.name = name
        self.sockobj = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.buff = ''
        self.msgs = []
        self.player = None
        self.in_game = False
        self.automated = auto
        self.prev_player_stat_list = None
        self.player_num = None
        if self.automated:
            self.gui = None
        else:
            self.gui = clientgui.ClientGui()
        logging.info('Client %s created', name)

    def connect(self, host, port):
        self.sockobj.connect((host, port))
        logging.info('Client %s succesfully connected to host: %s, port: %s',
            self.name, host, port)

    def send_msg(self, msg):
        logging.info('Client %s sending msg: %s', self.name, msg)
        msg = msg.encode('ascii')
        self.sockobj.send(msg)

    def recv_msgs(self):
        buff = self.sockobj.recv(1024)
        buff = buff.decode('ascii')
        self.buff += buff

        msg, self.buff = message.retrieve_msg_from_buff(self.buff)
        while msg:
            self.msgs.append(msg)
            logging.info('Client %s received message: %s', self.name, msg)
            msg, self.buff = message.retrieve_msg_from_buff(self.buff)

    def get_msg(self):
        if self.msgs:
            ret = self.msgs[0]
            self.msgs = self.msgs[1:]
            return ret
        else:
            return None

    def game_loop(self):
        # worker_pool = Pool(processes=5)
        while True:
            if not self.msgs:
                self.recv_msgs()
            # worker_pool.map_async(self.process_msg, self.msgs)
            msg = self.get_msg()
            while msg:
                self.process_msg(msg)
                msg = self.get_msg()

    def my_turn_num(self, player_stat_list):
        assert(self.in_game)
        if self.player_num != None:
            return self.player_num
        else:
            for idx, player_stat in enumerate(player_stat_list):
                if player_stat.name == self.player.name:
                    self.player_num = idx
                    break
            else:
                raise(common.PlayerError(self.player,
                    'stabl missing this player'))
        return self.player_num
    
    def remove_players_who_are_out(self, player_stat_list):
        new_psl = []
        for player_stat in player_stat_list:
            if player_stat.num_cards > 0:
                new_psl.append(player_stat)
        return new_psl

    def detect_winner(self, player_stat_list, prev_player_stat_list):
        if not prev_player_stat_list:
            return None
        for i, ps in enumerate(player_stat_list):
            if ps.num_cards == 0 and prev_player_stat_list[i].num_cards != 0:
                # we have a winner!
                return ps
        else:
            return None

    def process_msg(self, msg):
        # validate msg
        fields = message.fields(msg)
        msg_type = message.msg_type(msg)

        # process based on msg_type
        if msg_type == 'sjoin':
            # logging.warn('Client %s received unexpected sjoin message',
                # self.name)
            pass
        elif msg_type == 'shand':
            if (self.player_num and self.prev_player_stat_list and 
                self.player_num == current_turn_num(self.prev_player_stat_list)):
                # this player just went
                if self.automated:
                    logging.warn("Automated player %s made an invalid play", self.name)
                else:
                    self.gui.print_msg("You made an invalid play you schmuck.")
            hand = message.msg_to_hand(msg)
            self.player.pickup_hand(hand)
            logging.info('Client %s succesfully picked up hand: ' + str(hand),
                self.name)
            self.in_game = True
        elif msg_type == 'stabl':
            self.process_stabl(msg)
        elif msg_type == 'slobb':
            lobby = message.slobb_to_lobby(msg)
            logging.info('Lobby update: {}'.format(repr(lobby)))
            if self.gui:
                self.gui.update_lobby(message.slobb_to_lobby(msg))
        else:
            logging.info('Client received msg: ' + msg)

    def process_stabl(self, msg):
        logging.info('Client %s processing stabl: ' + msg, self.name)
        psl = message.stabl_to_player_stat_list(msg)
        last_play = message.stabl_to_last_play(msg)

        winner = self.detect_winner(psl, self.prev_player_stat_list)
        asshole = False
        if winner:
            # see if the game is over
            active_players = []
            for player in psl:
                if player.status in ('a', 'w', 'p') and player.num_cards > 0:
                        active_players.append(player)
            assert(len(active_players) != 0)
            if len(active_players) == 1:
                # the game is over!
                self.in_game = False
                self.player.hand = []
                self.player.status = 'l'
                self.player_num = None
                asshole = active_players[0]
                self.prev_player_stat_list = None

        # update gui
        if self.gui:
            self.gui.update(psl, self.prev_player_stat_list,
                last_play, winner, asshole)
        if asshole:
            return

        if self.in_game:
            # see if it's their turn
            if current_turn_num(psl) == self.my_turn_num(psl):
                if self.automated:
                    time.sleep(.2)
                    play = self.auto_play(last_play)
                else:
                    play = self.gui.prompt_for_play(psl, self.player.hand)
                self.player.remove_from_hand(play)
                self.send_msg('[cplay|{}]'.format(message.cards_to_str(play, 4)))

        self.prev_player_stat_list = psl

    def auto_play(self, last_play):
        hand = self.player.hand
        hand.sort()
        if (len(last_play) == 0):
            # play lowest card
            return [hand[0]]
        elif (len(last_play) == 1):
            # play lowest card that beats it
            for card in hand:
                if card >= last_play[0]:
                    return [card]
        else:
            return []

    def disconnect(self):
        self.sockobj.close()
        logging.info('Client %s succesfully closed', self.name)

def usage():
    print(__doc__)

def parse_cmd_args(argv):
    manual, name = False, 'chipjack'    # defaults

    try:
        opts, args = getopt.getopt(argv, 'hs:p:n:m', ['help', 'host', 'port', 'name', 'manual'])

        for opt, arg in opts:
            if opt in ('-h', '--help'):
                usage()
                sys.exit()
            elif opt in ('-s', '--host'):
                common.HOST = arg
            elif opt in ('-p', '--port'):
                common.PORT = arg
            elif opt in ('-m', '--manual'):
                manual = True
            elif opt in ('-n', '--name'):
                name = arg
            else:
                raise getopt.GetoptError(msg='Invalid command line option')

    except getopt.GetoptError as ex:
        print(ex.msg)
        usage()
        sys.exit()
    else:
        return manual, name

def main(argv):
    manual, name = parse_cmd_args(argv)
    auto = not manual

    client = Client(name, auto=auto)
    client.connect(common.HOST, common.PORT)

    # join the server
    client.send_msg('[cjoin|{}]'.format(name))
    while not client.msgs:
        client.recv_msgs()

    msg = client.get_msg()
    while message.msg_type(msg) != 'sjoin':
        # logging.warn('Client {} received an unexpected message: {}'.format(client.name, msg))
        msg = client.get_msg()
    
    # validate msg
    name = message.fields(msg)[0].strip()
    client.player = common.Player(name)
    logging.info('Client {} successfully joined with name {}'.format(client.name, name))

    client.game_loop()

    client.disconnect()


if __name__ == '__main__':
    # common.setup_logging()
    main(sys.argv[1:])
    # logging.info('Logging finished')
    
#    client = Client('localhost', 36789, 'chipjack')
#    names = [
#        'hiprack ',
#        'lcp69   ',
#        'chipple ',
#        'nipple  ',
#        'ch8_px__',
#        'BillyBo ',
#        'bonnyho ',
#        'Tman    ',
#        'chipdrip',
#        ]
#    for name in names:
#        client = Client('localhost', 36789, name, auto=True)
#    asyncore.loop()
