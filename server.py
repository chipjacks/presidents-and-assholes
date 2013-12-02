
"""
Description:
    Blah blah blah

Usage:
    python3 server.py ...

"""
import common
import socket
import asyncore
import message
import logging
import threading
import time
import queue
import getopt
import sys

MAX_CLIENTS = 20

table = common.Table()
lobby = []
client_to_player = {}
player_to_client = {}
server = None

class PlayerHandler(asyncore.dispatcher_with_send):

    def __init__(self, uid, sock=None, map=None):
        asyncore.dispatcher_with_send.__init__(self, sock)
        self._uid = uid
        self.player = None
        self.buff = ''
        self.msgs = []

    def add_to_buffer(self, str):
        logging.debug('Sending: {}'.format(str))
        self.out_buffer += bytes(str, 'ascii')

    def handle_read(self):
        buff = self.recv(1024)
        buff = buff.decode('ascii')
        self.buff += buff

        msg, self.buff = message.retrieve_msg_from_buff(self.buff)
        while msg:
            self.msgs.append(msg)
            logging.info('Server received message: %s', msg)
            msg, self.buff = message.retrieve_msg_from_buff(self.buff)

        self.parse_msgs()

    def parse_msgs(self):
        msgs = self.msgs
        self.msgs = []
        for msg in msgs:
            if not message.is_valid(msg):
                logging.warn('Message flagged invalid: %s', msg)
                self.send_strike('30')
                # need to add other strike codes
                return
            msg_type = message.msg_type(msg) 
            if msg_type == 'cjoin':
                self.handle_cjoin(msg)
            elif msg_type == 'cplay':
                self.handle_cplay(msg)

    def handle_cjoin(self, msg):
        fields = message.fields(msg)
        assert(len(fields) == 1)
        assert(len(fields[0]) == 8)
        if self.player:
            # we already initialized the player
            raise common.PlayerError(self.player, 'invalid cjoin')
        # check if name needs to be mangled
        name = fields[0]
        # add the player to the table or the lobby
        self.player = common.Player(name)
        client_to_player[self] = self.player
        player_to_client[self.player] = self
        if table.full():
            logging.info('Player added to lobby: {}'.format(name))
            lobby.append(self.player)
            server.send_slobb()
        else:
            logging.info('Player added to table: {}'.format(name))
            server.add_player_to_table(self._uid, self.player)
        # reply with sjoin
        self.add_to_buffer('[sjoin|{}]'.format(name))

    def handle_cplay(self, msg):
        fields = message.fields(msg)
        assert(len(fields) == 1)
        cards = message.str_to_cards(fields[0])
        server.new_play = True
        try:
            table.play_cards(self.player, cards)
        except common.PlayerError as ex:
            logging.warn(ex)
            self.send_strike(ex.strike_code)
            self.send_shand()
        else:
            # successfull play
            logging.info('Player {} succesfully played: {}'.format(
                self.player.name, repr(cards)))
            # see if the game is over
            if len(table.active_players()) <= 1:
                server.finish_game()
        finally:
            server.send_stabl()

    def send_shand(self):
        msg = message.hand_to_msg(self.player.hand)
        self.add_to_buffer(msg)

    def send_strike(self, code):
        logging.info('Sending strike to client %s', self.player.name)
        self.player.strikes += 1
        self.add_to_buffer('[strik|{}|{}]'.format(code, self.player.strikes))
        if self.player.strikes >= 3:
            # kick him
            self.handle_close()

    def handle_close(self):
        server.handle_client_disconnect(self._uid)
        player_to_client.pop(self.player, None)
        if self.player in table.players:
            self.player.status = 'd'
            logging.info('Player {} left the table'.format(self.player.name))
        elif self.player in lobby:
            logging.info('Player {} left the lobby'.format(self.player.name))
            lobby.remove(self.player)
            # send a lobby update message
            server.send_slobb()
        elif self.player in table.winners:
            logging.info('Player {} left the winners circle'.format(
                self.player.name))
            table.winners.remove(self.player)
        elif self.player:
            logging.warn('Player {} can\'t be found'.format(self.player.name))
        if len(table.active_players()) <= 1:
            server.finish_game()
        self.close()

class GameServer(asyncore.dispatcher):

    def __init__(self, host, port):
        asyncore.dispatcher.__init__(self)
        self.create_socket()
        self.set_reuse_addr()
        self.bind((host, port))
        self.listen(5)
        self._next_uid = 1
        self.clients = {} 
        self.clients_at_table = []
        table.starting_round = True
        self.new_play = True
    
    def add_player_to_table(self, uid, player):
        player.status = 'w'
        table.add_player(player)
        self.clients_at_table.append(uid)

    def remove_player_from_table(self, uid, player):
        table.remove_player(player)
        self.clients_at_table.remove(uid)

    def handle_accepted(self, sock, addr):
        logging.debug('Incoming connection from %s' % repr(addr))
        handler = PlayerHandler(self._next_uid, sock)
        self.clients[self._next_uid] = handler
        self._next_uid += 1

    def handle_close(self):
        logging.info('Closing GameServer')
        self.close()

    def handle_client_disconnect(self, uid):
        client = self.clients.pop(uid, None)
        try:
            self.clients_at_table.remove(uid)
        except ValueError:
            pass
        client_to_player.pop(client, None)

    def send_stabl(self):
        msg = message.table_to_stabl(table)
        logging.info('Client broadcast: ' + msg)
        for client in self.clients.values():
            client.add_to_buffer(msg)

    def send_slobb(self):
        if not lobby:
            return
        msg = message.lobby_to_slobb(lobby)
        logging.info('Server broadcasting: ' + msg)
        for client in self.clients.values():
            client.add_to_buffer(msg)

    def send_hands(self):
        hands = table.deal()
        assert(len(table.players) == len(hands))
        assert(len(self.clients_at_table) == len(hands))
        for player in table.players:
            msg = message.hand_to_msg(player.hand)
            player_to_client[player].add_to_buffer(msg)

        # negotiate president, asshole swap
        table.players[0].status = 'a'

    def play_timedout(self):
        who = None
        # figure out whose turn it was
        for player in table.players:
            if player.status == 'a':
                who = player
                break
        else:
            logging.warn('Play timed out, but no player active.')
            return
        client = player_to_client[who]
        # pass for him
        table.play_cards(who, [])
        client.send_strike('20')
        self.send_stabl()

    def finish_game(self):
        global lobby
        logging.warn('Game ended, new game starting')
        # send one last stabl
        self.send_stabl()
        table.starting_round = False
        table.turn = 0
        active_players = table.active_players()
        assert(len(active_players) <= 1)
        if active_players:
            # get the asshole off the table
            table.winners.append(active_players[0])
        table.players = []
        self.clients_at_table = []
        old_players = []
        new_players = []

        # get people from the lobby
        if len(lobby) > 7:
            new_players = lobby[0:7]
            lobby = lobby[7:]
            lobby += table.winners
        else:
            new_players = lobby
            lobby = []
            num_old_players = common.TABLESIZE - len(new_players)
            if len(table.winners) < num_old_players:
                old_players = table.winners
            else:
                old_players = table.winners[0:num_old_players]
                assert(len(old_players) == num_old_players)
                # move rest of winners to lobby
                lobby += table.winners[num_old_players:]
        
        table.winners = []
        table.played_cards = []
        for player in old_players:
            self.add_player_to_table(player_to_client[player]._uid, player)
        for player in new_players: 
            self.add_player_to_table(player_to_client[player]._uid, player)

        # send a lobby update message
        server.send_slobb()

        start_game()



def start_server():
    global server
    server = GameServer(common.HOST, common.PORT)

def process_requests():
    asyncore.loop(timeout=0.1, count=1)

def start_server_in_thread():
    server_thread = threading.Thread(target=main)
    server_thread.start()
    return server, server_thread

def wait_for_players():
    timeout = time.time() + 5  # 30 seconds from now
    while asyncore.socket_map:
        asyncore.loop(timeout=0.5, count=1)
        if time.time() > timeout or table.full():
            break

def main_loop():
    turntimeout = time.time() + 15
    while asyncore.socket_map:
        if len(table.players) <= 0:
            # games over, everyone bailed
            logging.info('Game ended because too many people bailed')
            server.finish_game()
        # wait for players to play
        turntimeleft = turntimeout - time.time()
        asyncore.loop(timeout=turntimeleft, count = 1)
        if server.new_play:
            server.new_play = False
            turntimeout = time.time() + 15
        else:
            if turntimeout - time.time() <= 0.1:
                # the client timed out
                server.play_timedout()
                turntimeout = time.time() + 15
            else:
                # they still have some time
                pass

def usage():
    print(__doc__)

def parse_cmd_args(argv):
    turntimeout, lobbytimeout, minplayers = 15, -1, 3 # defaults

    try:
        opts, args = getopt.getopt(argv, 'ht:l:m:s:', ['help', 'turntimeout', 'minplayers', 'lobbytimeout', 'host'])

        for opt, arg in opts:
            if opt in ('-h', '--help'):
                usage()
                sys.exit()
            elif opt in ('-t', '--turntimeout'):
                turntimeout = arg
            elif opt in ('-l', '--lobbytimeout'):
                lobbytimeout = arg
            elif opt in ('-m', '--minplayers'):
                minplayers = arg
            elif opt in ('-s', '--host'):
                common.HOST = arg
            else:
                raise getopt.GetoptError(msg='Invalid command line option')

    except getopt.GetoptError as ex:
        print(ex.msg)
        usage()
        sys.exit()
    else:
        return turntimeout, lobbytimeout, minplayers

def start_game():
    while not table.ready():
        wait_for_players()
        logging.info('Table not ready, players: {}'.format(repr(table.players)))

    logging.info('Table ready, game starting, number players: {}'.format(len(table.players)))
    
    # deal the cards
    server.send_hands()

    # send the initial stabl
    server.send_stabl()

    # start the game
    main_loop()

def main(argv):
    turntimeout, lobbytimeout, minplayers = parse_cmd_args(argv)

    start_server()
    logging.info('Game server started')

    start_game()


if __name__ == '__main__':
    common.setup_logging()
    main(sys.argv[1:])
