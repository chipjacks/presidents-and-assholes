"""
Description:
    Client to play warlords and scumbags game

Usage:
    python3 client.py <args>

Command line arguments:
    -h, --help  Print this help.

    -s, --host  Host name of server to connect to.
                    e.g. 192.168.10.1 or localhost.

    -p, --port  Port to connect to.

    -n, --name  Player name to use in game.
    
    -m, --manual    Manual mode. Text based UI will be displayed in terminal
                    to play game in. Otherwise an automated client will be
                    spawned which will automatically play cards and no UI will
                    be displayed.
"""

import sys
import common
import message
import logging
import clientgui
import socket
import getopt
import time
import threading
import queue

AUTOPLAY_PAUSE = 2  # seconds automated client waits before sending play to server

def current_turn_num(player_stat_list):
    """Calculates what turn number it is from player_stat_list."""
    assert(player_stat_list)
    for i, player_stat in enumerate(player_stat_list):
        if player_stat.status == 'a':
            return i
    else:
        # game could be over
        logging.info('Server sent stabl with no one active.')
        return -1

class Client():
    """Main client class that controls communication with server. Spawns GUI for
    player to play in if manual mode is specified with command line arguments.
    """

    # Set-up
    def __init__(self, name, host, port, auto=True):
        self.automated = auto
        self.run = True
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
        self.waiting_for_play = False
        self.waiting_for_swap = False
        self.player = None
        self.in_game = False
        self.prev_player_stat_list = None
        self.player_num = None
        self.wait_thread = None
        logging.info('Client %s created', name)

    def connect(self, host, port):
        """Connect to server socket"""
        self.sockobj.connect((host, port))
        logging.info('Client %s succesfully connected to host: %s, port: %s',
            self.name, host, port)
        if self.gui: self.gui.print_msg("Succesfully connected to server, waiting for join confirmation.")

    # Socket communication
    def send_msg(self, msg):
        """Send message through socket to server"""
        assert(msg)
        logging.info('Client %s sending msg: %s', self.name, msg)
        msg = msg.encode('ascii')
        try_num = 1
        while try_num <= 3:
            try:
                sent = self.sockobj.send(msg)
                if sent == 0:
                    self.run = False
            except IOError as e:
                logging.info('Client %s: IOError when trying to send: , %s',
                    self.name, e)
                # server kicked us?
                self.run = False
                break
            except socket.timeout as e:
                # try again
                logging.info('Timeout when trying to send')
                try_num += 1
                continue
            else:
                # succesful send
                break

    def recv_msgs(self):
        """Receive data from server socket and put them in buffer"""
        try:
            buff = self.sockobj.recv(1024)
            if not buff:
                # looks like socket is closed
                self.run = False
                return
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
        """Get first message from list of messages waiting to be processed"""
        if self.msgs:
            ret = self.msgs[0]
            self.msgs = self.msgs[1:]
            return ret
        else:
            return None

    # Main loop, message processing
    def game_loop(self):
        """Main loop. Receives messages, and processes them in order."""
        while self.run:
            # cleanup any zombie threads
            self.cleanup_wait_thread()
            # get msgs from socket
            if not self.msgs:
                self.recv_msgs()
            msg = self.get_msg()
            # process msgs
            while msg:
                self.process_msg(msg)
                msg = self.get_msg()

    def process_msg(self, msg):
        """Process message based on type."""
        if not message.is_valid(msg):
            logging.info("Client %s received invalid message: %s", self.name, 
                msg)
            return
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
                    logging.info("Automated player %s made an invalid play",
                        self.name)
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
            if self.gui:
                self.gui.update_chat(who, what)
        elif msg_type == 'swapw':
            # notifies warlord of swap offer from scumbag
            fields = message.fields(msg)
            card = int(fields[0])
            if self.gui:
                # figure out what card the player wants to send the scumbag
                self.gui.print_msg("Received card from scumbag: {}".format(
                    self.gui.print_card(card)))
                self.gui.print_msg(
                    "Please play the card you would like to send to the scumbag")
                self.waiting_for_swap = True
                self.waiting_for_play = False
                self.asynch_get_play()
            else:
                if not self.player.hand:
                    logging.info("Warlord offered a swap before they knows there hand")
                    # we need to wait for our hand, hopefully it is in the socket
                    self.recv_msgs()
                    # gonna have to come back to this msg later
                    self.msgs.append(msg)
                else:
                    # automated, send lowest card
                    self.send_msg('[cswap|{0:02d}]'.format(
                        min(self.player.hand)))
                    self.player.hand.remove(min(self.player.hand))
        elif msg_type == 'swaps':
            # notifies scumbag that a swap has occurred
            fields = message.fields(msg)
            card_gained = int(fields[0])
            card_lost = int(fields[1])
            if self.gui:
                self.gui.print_msg(
                    "As the scumbag, you were forced to trade your {} for the presidents {}".format(
                    self.gui.print_card(card_lost),
                    self.gui.print_card(card_gained)))
        elif msg_type == 'strik':
            fields = message.fields(msg)
            code = fields[0]
            if self.waiting_for_swap and code == 20:
                # timeout on swap
                logging.info('Client timed out on sending cswap')
                if self.gui:
                    self.gui.print_msg(
                        "You ran out of time to send a card to the scumbag".format(
                        code))
                self.waiting_for_swap = False
            else:
                logging.info('Client %s received strike, code: %s', self.name, 
                    code)
                if self.gui:
                    self.gui.print_msg(
                        "Received strike (code {}) from server".format(code))
        else:
            logging.info('Client received msg: ' + msg)

    def process_stabl(self, msg):
        """Process table status message, prompt user for play if necessary."""
        logging.info('Client %s processing stabl: ' + msg, self.name)
        psl = message.stabl_to_player_stat_list(msg)
        last_play = message.stabl_to_last_play(msg)

        winner = self.detect_winner(psl, self.prev_player_stat_list)
        asshole = False

        # update gui
        if self.gui:
            self.gui.update(psl, self.prev_player_stat_list,
                last_play, winner, asshole)
        if winner:
            if winner.name.strip() == self.player.name.strip():
                # they went out
                if self.gui:
                    self.gui.print_msg("You went out!")
            # see if the game is over
            active_players = []
            for player in psl:
                if player.status in ('a', 'w', 'p') and player.num_cards > 0:
                    active_players.append(player)
            if len(active_players) <= 1:
                # the game is over!
                self.in_game = False
                self.waiting_for_play = False
                self.player.hand = []
                self.player.status = 'l'
                self.player_num = None
                self.cleanup_wait_thread()
                self.wait_thread = None
                try:
                    asshole = active_players[0]
                except IndexError:
                    asshole = None
                self.prev_player_stat_list = None
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
                    play = self.auto_play(last_play)
                    self.player.remove_from_hand(play)
                    self.send_msg('[cplay|{}]'.format(message.cards_to_str(play, 4)))
                else:
                    self.waiting_for_play = True
                    self.gui.print_msg("It's your turn!")
                    self.asynch_get_play()
        self.prev_player_stat_list = psl

    # Utility functions
    def my_turn_num(self, player_stat_list):
        """Looks through player list and determines what turn number client is
        at table.
        """
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
    
    def detect_winner(self, player_stat_list, prev_player_stat_list):
        """See if anyone won between the two latest table status messages from
        the server.
        """
        if not prev_player_stat_list:
            return None
        for i, ps in enumerate(player_stat_list):
            if ps.num_cards == 0 and prev_player_stat_list[i].num_cards != 0:
                # we have a winner!
                return ps
        else:
            return None

    def asynch_get_play(self):
        """Asynchronously get user play from GUI."""
        assert(self.gui)
        if self.wait_thread:
            self.wait_thread.join(0)
            if self.wait_thread.is_alive():
                logging.info("Client %s tried to start multiple threads waiting " +
                    "for gui input")
                return
        self.wait_thread = threading.Thread(target=self.get_play)
        self.wait_thread.start()
    
    def get_play(self):
        """Get user play from GUI."""
        assert(self.gui)
        while self.waiting_for_play or self.waiting_for_swap:
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
                elif self.waiting_for_swap:
                    # still waiting, swap it
                    self.waiting_for_swap = False
                    self.player.remove_from_hand(list(play[:1]))
                    self.send_msg('[cswap|{}]'.format(
                        message.cards_to_str(play[:1], 1)))
                    if self.gui:
                        self.gui.print_msg("Sent swap")
                        self.gui.print_hand(self.player.hand)
                    return
                else:
                    if self.gui:
                        self.gui.print_msg("Wait for your turn to play")
        return
                    
    def cleanup_wait_thread(self):
        """Check for zombie threads and clean them up."""
        if not self.wait_thread:
            return
        else:
            self.wait_thread.join(0)
        if not self.wait_thread.is_alive():
            self.wait_thread = None

    def auto_play(self, last_play):
        """When client is automated, figure out which cards to play."""
        time.sleep(AUTOPLAY_PAUSE)
        hand = self.player.hand
        hand.sort()
        if (len(last_play) == 0):
            # play lowest card
            return [hand[0]]
        elif (len(last_play) == 1):
            if last_play[0] // 4 == 12:
                # it was a two, you get to go again
                return [hand[0]]
            # play lowest card that beats it
            for card in hand:
                if card >= last_play[0]:
                    return [card]
        else:
            return []

    def disconnect(self):
        """Disconnect socket from server."""
        try:
            self.sockobj.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
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
    client = None

    try:
        if auto:
            common.setup_logging()
        else:
            FORMAT = '%(filename)s: %(message)s'
            logging.basicConfig(level=logging.DEBUG, format=FORMAT,
                filename='client.log')
            logging.info('Logging started')
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

        if client.gui: client.gui.print_msg("Quitting, press any key to confirm")

        client.disconnect()

        if client.gui:
            client.gui.curses_thread.join()
        logging.info("Client %s quitting", client.name)
    except Exception as ex:
        logging.info('Client caught exception: %s', ex)
        raise ex
    return

if __name__ == '__main__':
    main(sys.argv[1:])
    logging.info('Logging finished')
