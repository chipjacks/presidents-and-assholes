import common
import message
import logging
import clientgui
import socket
import getopt
import sys
import time
import threading
import queue

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
    def __init__(self, name, host, port, auto=True):
        self.automated = auto
        if self.automated:
            self.gui = None
        else:
            self.gui = clientgui.ClientGui(self)
        self.name = name
        self.sockobj = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sockobj.settimeout(1)
        self.connect(host, port)
        self.buff = ''
        self.msgs = []
        self.run = True
        self.waiting_for_play = False
        self.player = None
        self.in_game = False
        self.prev_player_stat_list = None
        self.player_num = None
        self.wait_thread = None
        logging.info('Client %s created', name)

    def connect(self, host, port):
        self.sockobj.connect((host, port))
        logging.info('Client %s succesfully connected to host: %s, port: %s',
            self.name, host, port)
        if self.gui: self.gui.print_msg("Succesfully connected to server, waiting for join confirmation.")

    def send_msg(self, msg):
        assert(msg)
        logging.info('Client %s sending msg: %s', self.name, msg)
        msg = msg.encode('ascii')
        try_num = 1
        while try_num <= 3:
            try:
                self.sockobj.send(msg)
            except IOError as e:
                logging.info('IOError when trying to send: , %s', e)
                # server kicked us?
                self.run = False
            except socket.timeout as e:
                # try again
                logging.info('Timeout when trying to send')
                try_num += 1
                continue
            else:
                break

    def recv_msgs(self):
        try:
            buff = self.sockobj.recv(1024)
        except ConnectionResetError as e:
            logging.info('ConnectionResetError when trying to receive: %s', e)
            self.run = False
            return
        except socket.timeout as e:
            return
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
        while self.run:
            if self.wait_thread:
                self.wait_thread.join(0)
                if not self.wait_thread.is_alive():
                    self.wait_thread = None
            if not self.msgs:
                self.recv_msgs()
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
                    logging.info("Automated player %s made an invalid play", self.name)
                else:
                    self.gui.print_msg("You made an invalid play you schmuck.")
            hand = message.msg_to_hand(msg)
            assert(hand)
            self.player.pickup_hand(hand)
            logging.info('Client %s succesfully picked up hand: ' + str(hand),
                self.name)
            if self.gui:
                self.gui.print_hand(hand)
                self.gui.print_msg("Picked up hand")
            self.in_game = True
        elif msg_type == 'stabl':
            self.process_stabl(msg)
        elif msg_type == 'slobb':
            lobby = message.slobb_to_lobby(msg)
            logging.info('Lobby update: {}'.format(repr(lobby)))
            if self.gui:
                self.gui.update_lobby(message.slobb_to_lobby(msg))
        elif msg_type == 'schat':
            fields = message.fields(msg)
            who = fields[0]
            what = fields[1]
            self.gui.update_chat(who, what)
        else:
            logging.info('Client received msg: ' + msg)

    def asynch_get_play(self):
        self.wait_thread = threading.Thread(target=self.get_play)
        self.wait_thread.start()
    
    def get_play(self):
        assert(self.gui)
        while self.waiting_for_play:
            try:
                play = self.gui.pending_play.get(timeout=5)
            except queue.Empty:
                continue
            else:
                if self.waiting_for_play:
                    # still waiting, play it
                    self.waiting_for_play = False
                    self.player.remove_from_hand(play)
                    self.send_msg('[cplay|{}]'.format(
                        message.cards_to_str(play, 4)))
                    if self.gui:
                        self.gui.print_msg("Sent play")
                        self.gui.print_hand(self.player.hand)
                    return
                else:
                    break
        self.gui.print_msg("Play didn't go through")
        return
                    
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
            # see if they missed their turn
            if self.waiting_for_play and \
                current_turn_num(psl) != self.my_turn_num(psl):
                # their turn timed out
                self.waiting_for_play = False
                if not self.wait_thread.is_alive():
                    self.wait_thread = None
            # see if it's their turn
            if current_turn_num(psl) == self.my_turn_num(psl):
                if self.automated:
                    time.sleep(.2)
                    play = self.auto_play(last_play)
                    self.player.remove_from_hand(play)
                    self.send_msg('[cplay|{}]'.format(message.cards_to_str(play, 4)))
                else:
                    self.waiting_for_play = True
                    self.gui.print_msg("It's your turn!")
                    self.asynch_get_play()

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
        self.sockobj.shutdown(socket.SHUT_RDWR)
        self.sockobj.close()
        logging.info('Client %s succesfully closed', self.name)
        if self.gui: self.gui.print_msg("Disconnected from server")

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
                common.PORT = int(arg)
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

    client = Client(name, common.HOST, common.PORT, auto=auto)

    # join the server
    client.send_msg('[cjoin|{}]'.format(name.ljust(8)))
    while not client.msgs:
        client.recv_msgs()

    msg = client.get_msg()
    assert msg, 'No msg, self.msgs = '.format(client.msgs)
    while message.msg_type(msg) != 'sjoin':
        # logging.warn('Client {} received an unexpected message: {}'.format(client.name, msg))
        msg = client.get_msg()
    
    # validate msg
    name = message.fields(msg)[0].strip()
    client.player = common.Player(name)
    logging.info('Client {} successfully joined with name {}'.format(client.name, name))
    if client.gui:
        client.gui.print_msg("Succesfully joined server with name {}".format(
            client.player.name))

    client.game_loop()

    if client.gui: client.gui.print_msg("Quitting..")

    client.disconnect()

    if client.gui:
        client.gui.curses_thread.join()
    logging.info("Client quitting")
    return


if __name__ == '__main__':
    common.setup_logging()
    main(sys.argv[1:])
    logging.info('Logging finished')
    
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
