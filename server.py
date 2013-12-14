
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
import re
import random

MAX_CLIENTS = 20
TURNTIMEOUT = 15
LOBBYTIMEOUT = 15
MINPLAYERS = 3
RUNNING = False

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
        self.strikes = 0  # for before player is initialized

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

        if len(self.buff) > 1000:
            # must be filled with crap
            self.buff = ''
            self.send_strike('32')

        self.parse_msgs()

    def parse_msgs(self):
        msgs = self.msgs
        self.msgs = []
        for msg in msgs:
            if not message.is_valid(msg):
                logging.info('Message flagged invalid: %s', msg)
                self.send_strike('30')
                # need to add other strike codes
                return
            msg_type = message.msg_type(msg) 
            if msg_type == 'cjoin':
                self.handle_cjoin(msg)
            elif msg_type == 'cplay':
                self.handle_cplay(msg)
            elif msg_type == 'cchat':
                self.handle_cchat(msg)
            elif msg_type == 'cswap':
                server.handle_cswap(self, msg)
            elif msg_type == 'chand':
                self.send_shand()

    def handle_cjoin(self, msg):
        global lobby
        fields = message.fields(msg)
        assert(len(fields) == 1)
        assert(len(fields[0]) == 8)
        if self.player:
            # we already initialized the player
            raise common.PlayerError(self.player, 'invalid cjoin')
        # check if name needs to be mangled
        name = fields[0].strip()
        current_names = [player.name for player in lobby]
        current_names += [player.name for player in table.players]
        name = mangle_name(current_names, name)

        # add the player to the table or the lobby
        self.player = common.Player(name)
        self.player.strikes = self.strikes
        client_to_player[self] = self.player
        player_to_client[self.player] = self
        logging.info('Player added to lobby: {}'.format(name))
        lobby.append(self.player)
        server.send_slobb()
        # reply with sjoin
        self.add_to_buffer('[sjoin|{}]'.format(name.ljust(8)))

    def handle_cplay(self, msg):
        fields = message.fields(msg)
        assert(len(fields) == 1)
        cards = message.str_to_cards(fields[0])
        server.new_play = True
        try:
            if server.first_play:
                if table.starting_round and 0 not in cards:
                    # they have to play the 3 of clubs on the first play
                    self.send_strike('16')
                    self.send_shand()
                    return
                elif not cards:
                    # they can't pass on first play
                    self.send_strike('18')
                    return
                else:
                    table.validate_play(self.player, cards)
                    server.first_play = False
            table.play_cards(self.player, cards)
        except common.PlayerError as ex:
            logging.info(ex)
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

    def handle_cchat(self, msg):
        assert(message.msg_type(msg) == 'cchat')
        fields = message.fields(msg)
        assert(len(fields) == 1)
        chat = fields[0].strip()
        if not self.player:
            # client hasn't sent cjoin
            self.send_strike('30')
            return
        name = self.player.name
        server.send_schat(name, chat)

    def send_shand(self):
        if not self.player or not self.player.hand:
            return
        msg = message.hand_to_msg(self.player.hand)
        self.add_to_buffer(msg)

    def send_strike(self, code):
        if self.player:
            name = self.player.name
            self.player.strikes += 1
            strikes = self.player.strikes
        else:
            name = '(player name not initialized)'
            self.strikes += 1
            strikes = self.strikes
        logging.info('Sending strike to client %s', name)
        self.add_to_buffer('[strik|{}|{}]'.format(code, strikes))
        if self.player.strikes >= 3:
            # kick em
            self.handle_close()

    def handle_close(self):
        global lobby
        if self.player in table.players:
            if self.player.status == 'a':
                # pass for them
                self.player.status = 'd'
                active_players = table.active_players()
                if len(active_players) <= 1:
                    table.turn = 0
                    server.finish_game()
                else:
                    table.turn %= len(active_players)
                    active_players[table.turn].status = 'a'
                server.new_play = True
            else:
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
            logging.info('Player {} can\'t be found'.format(self.player.name))
        # server.handle_client_disconnect(self._uid)
        # player_to_client.pop(self.player, None)
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
        self.first_play = True
        self.swap_timeout = None
    
    def add_player_to_table(self, uid, player):
        assert(len(table.players) == len(self.clients_at_table))
        player.status = 'w'
        if table.add_player(player):
            self.clients_at_table.append(uid)
        else:
            logging.info("tried to add played to table when already full")
        assert(len(table.players) == len(self.clients_at_table))

    def remove_player_from_table(self, uid, player):
        table.remove_player(player)
        self.clients_at_table.remove(uid)

    def handle_accepted(self, sock, addr):
        logging.debug('Incoming connection from %s' % repr(addr))
        if len(lobby) >= common.LOBBYSIZE:
            # lobby is full
            return
        handler = PlayerHandler(self._next_uid, sock)
        self.clients[self._next_uid] = handler
        self._next_uid += 1

    def handle_close(self):
        logging.info('Closing GameServer')
        self.close()
    
    def shutdown(self):
        self.handle_close()
        while True:
            try:
                client = self.clients.popitem()
                client[1].handle_close()
            except KeyError:
                return


    def handle_client_disconnect(self, uid):
        client = self.clients.pop(uid, None)
        try:
            self.clients_at_table.remove(uid)
            table.remove_player(client.player)
        except ValueError:
            pass
        except AttributeError:
            pass
        client_to_player.pop(client, None)

    def send_stabl(self):
        msg = message.table_to_stabl(table)
        logging.info('Client broadcast: ' + msg)
        for client in self.clients.values():
            client.add_to_buffer(msg)

    def send_slobb(self):
        global lobby
        msg = message.lobby_to_slobb(lobby)
        logging.info('Server broadcasting: ' + msg)
        for client in self.clients.values():
            client.add_to_buffer(msg)

    def send_schat(self, name, chat):
        assert(len(chat) <= 63)
        msg = '[schat|{}|{}]'.format(name.ljust(8), chat.ljust(63))
        logging.info('Server broadcasting: ' + msg)
        for client in self.clients.values():
            client.add_to_buffer(msg)

    def send_hands(self):
        hands = table.deal()
        assert(len(table.players) == len(hands))
        assert(len(self.clients_at_table) == len(hands))
        if table.starting_round:
            # don't need to perform warlord-scumbag swap
            for player in table.players:
                player_to_client[player].send_shand()
                if 0 in player.hand:
                    # they have the 3 of clubs
                    player.status = 'a'
        else:
            logging.info("Initiating warlord-scumbag swap")
            for player in table.players[1:-1]:
                player_to_client[player].send_shand()
            # send warlord hand and swapw
            warlord = table.players[0]
            scumbag = table.players[-1]
            card_from_scum = max(scumbag.hand)
            warlord.hand.append(card_from_scum)
            player_to_client[warlord].send_shand()
            msg = '[swapw|{}]'.format(card_from_scum)
            player_to_client[warlord].add_to_buffer(msg)
            
            # wait for response
            logging.info("Offered warlord swap, waiting for response")
            self.swap_timeout = time.time() + TURNTIMEOUT
            while asyncore.socket_map:
                asyncore.loop(timeout=0.5, count=1)
                if not self.swap_timeout:
                    # the warlord sent the cswap
                    # remove the card from the scumbags hand
                    scumbag.hand.remove(card_from_scum)
                    # send the scumbag swaps
                    msg = '[swaps|{}|{}]'.format(scumbag.hand[-1], card_from_scum)
                    player_to_client[scumbag].add_to_buffer(msg)
                    logging.info("Swap completed succesfully")
                    break
                elif time.time() > self.swap_timeout:
                    logging.info("Warlord timed out in swap, giving original hand")
                    # swap timed out
                    # send warlord strike
                    player_to_client[warlord].send_strike('20')
                    # resend warlord his old hand
                    warlord.hand.remove(card_from_scum)
                    player_to_client[warlord].send_shand()
                    # send swaps to scumbag
                    player_to_client[scumbag].add_to_buffer('[swaps|52|52]')
                    # reset the timeout
                    self.swap_timeout = None
                    break
            # send scumbag his hand
            msg = message.hand_to_msg(scumbag.hand)
            player_to_client[scumbag].send_shand()
            # set the warlord's status to active
            table.players[0].status = 'a'
            self.first_play = True
                
    def handle_cswap(self, client, msg):
        if not self.swap_timeout:
            # we are not waiting for a swap, this is invalid
            logging.info("Unexpected cswap message received")
            client.send_strike('72')
            return
        else:
            # check if client is warlord
            if client != player_to_client[table.players[0]]:
                # not the warlord
                client.send_strike('71')
                logging.info("Non-warlord client sent swapw")
                return
            # check that the warlord has the card
            card = int(msg[7:9])
            if card not in client.player.hand:
                # doesn't have the card, let them try again
                logging.info("Warlord tried to swap a card they don't have, " +
                    "going to let them try again")
                client.send_strike('70')
                client.send_shand()
                self.swap_timeout += TURNTIMEOUT
                return
            # passed all checks, move card into scumbags hand
            client.player.hand.remove(card)
            table.players[-1].hand.append(card)
            self.swap_timeout = None
            # send_hands will take care of the rest

    def play_timedout(self):
        who = None
        # figure out whose turn it was
        for player in table.players:
            if player.status == 'a':
                who = player
                break
        else:
            logging.info('Play timed out, but no player active.')
            server.finish_game()
            return
        client = player_to_client[who]
        # pass for him
        table.play_cards(who, [])
        client.send_strike('20')
        self.send_stabl()

    def finish_game(self):
        global lobby
        logging.info('Game ended, new game starting')
        # send one last stabl
        self.send_stabl()
        table.starting_round = False
        table.turn = 0
        table.played_cards = []
        active_players = table.active_players()
        assert(len(active_players) <= 1)
        if active_players:
            # get the asshole off the table
            table.winners.append(active_players[0])
        # reset the table
        table.players = []
        self.clients_at_table = []
        # add players back into lobby 
        lobby = table.winners + lobby
        table.winners = []

        # send a lobby update message
        server.send_slobb()

def mangle_name(current_names, name):
    name_regex = '^[a-zA-Z_]\w{0,7}$'
    if not re.match(name_regex, name):
        # name is invalid
        if re.match('\d', name[0]):
            # starts with a digit
            name = 'a' + name[1:]
        for i, c in enumerate(name):
            if not re.match('\w', c):
                name = name[:i] + 'a' + name[i+1:]
    # name should be valid now
    i, j = 0, 0
    while name in current_names:
        # mangle that beezy
        if len(name) < 8:
            # try adding a '1' to the end
            name += '1'
        elif i < 10:
            # try replacing last character with a digit
            name = name[:-1] + str(i)
            i += 1
        elif j < 10:
            name = name[:-2] + str(j) + name[-1]
            j += 1
        else:
            # give them a random number name
            name = 'a' + str(random.randrange(0, 9999999))
    return name


def start_server():
    global server
    global RUNNING
    RUNNING = True
    server = GameServer(common.HOST, common.PORT)

def start_server_in_thread():
    server_thread = threading.Thread(target=main)
    server_thread.start()
    return server, server_thread

def wait_for_players():
    global RUNNING
    global LOBBYTIMEOUT
    timeout = time.time() + LOBBYTIMEOUT
    while asyncore.socket_map and RUNNING:
        asyncore.loop(timeout=0.5, count=1)
        if time.time() > timeout or len(lobby) >= 7:
            break

def main_loop():
    global RUNNING
    global TURNTIMEOUT
    global lobby
    turntimeout = time.time() + TURNTIMEOUT
    while asyncore.socket_map and RUNNING:
        if len(table.players) < 2:
            server.finish_game()
            # start a new game
            while not len(lobby) >= MINPLAYERS:
                wait_for_players()
                logging.info('Table not ready, players: {}'.format([p.name for p in lobby]))

            # move players from lobby to table
            for player in lobby[:7]:
                try:
                    server.add_player_to_table(player_to_client[player]._uid, player)
                except KeyError as e:
                    pass
            lobby = lobby[7:]
            server.send_slobb()

            logging.info('Table ready, game starting, number players: {}'.format(len(lobby)))
            
            # deal the cards
            server.send_hands()

            # send the initial stabl
            server.send_stabl()
        # wait for players to play
        turntimeleft = turntimeout - time.time()
        if turntimeleft > 0:
            asyncore.loop(timeout=turntimeleft, count = 1)
        if server.new_play:
            server.new_play = False
            turntimeout = time.time() + TURNTIMEOUT
        else:
            if turntimeout - time.time() <= 0.1:
                # the client timed out
                server.play_timedout()
                turntimeout = time.time() + TURNTIMEOUT
            else:
                # they still have some time
                pass

def stop():
    global RUNNING
    RUNNING = False

def start_game():
    global RUNNING
    global lobby
    global MINPLAYERS
    while RUNNING:
#        try:
            while not len(lobby) >= MINPLAYERS:
                wait_for_players()
                logging.info('Table not ready, players: {}'.format([p.name for p in lobby]))

            # move players from lobby to table
            for player in lobby[:7]:
                server.add_player_to_table(player_to_client[player]._uid, player)
            lobby = lobby[7:]
            server.send_slobb()

            logging.info('Table ready, game starting, number players: {}'.format(len(lobby)))
            
            # deal the cards
            server.send_hands()

            # send the initial stabl
            server.send_stabl()

            # start the game
            main_loop()
#        except Exception as e:
#            logging.info('Caught exception %s', e)
#            continue

    # shutdown server
    server.shutdown()

# Main, command-line interaction

def usage():
    print(__doc__)

def parse_cmd_args(argv):
    turntimeout, lobbytimeout, minplayers = 15, 15, 3 # defaults

    try:
        opts, args = getopt.getopt(argv, 'ht:l:m:s:', ['help', 'turntimeout', 'minplayers', 'lobbytimeout', 'host'])

        for opt, arg in opts:
            if opt in ('-h', '--help'):
                usage()
                sys.exit()
            elif opt in ('-t', '--turntimeout'):
                turntimeout = int(arg)
            elif opt in ('-l', '--lobbytimeout'):
                lobbytimeout = int(arg)
            elif opt in ('-m', '--minplayers'):
                minplayers = int(arg)
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

def main(argv):
    global TURNTIMEOUT
    global LOBBYTIMEOUT
    global MINPLAYERS
    TURNTIMEOUT, LOBBYTIMEOUT, MINPLAYERS = parse_cmd_args(argv)

    start_server()
    logging.info('Game server started')

    start_game()

    logging.info('Game server shutdown')


if __name__ == '__main__':
    common.setup_logging()
    main(sys.argv[1:])
