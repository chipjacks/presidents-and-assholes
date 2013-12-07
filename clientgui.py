import message
import client
import curses
import curses.textpad
import threading
import queue
import subprocess
import sys
import time

SCRN_WIDTH = 100
MSGS_HEIGHT = 11
TABLE_HEIGHT = 11
LOBBY_WIDTH = 15
HAND_HEIGHT = 8
LOBBY_HEIGHT = HAND_HEIGHT + HAND_HEIGHT
HAND_WIDTH = SCRN_WIDTH - LOBBY_WIDTH
PLAY_WIDTH = SCRN_WIDTH // 3
CHAT_WIDTH = SCRN_WIDTH - PLAY_WIDTH
SEND_CHAT_WIDTH = SCRN_WIDTH // 2
PLAY_INPUT_WIDTH = SCRN_WIDTH // 4
BEAT_WIDTH = SCRN_WIDTH - SEND_CHAT_WIDTH - PLAY_INPUT_WIDTH
PLAY_CHAT_HEIGHT = 10
INPUT_HEIGHT = 5
SCRN_HEIGHT = MSGS_HEIGHT + TABLE_HEIGHT + HAND_HEIGHT + \
    PLAY_CHAT_HEIGHT + INPUT_HEIGHT

HELP_MSG = """
HELP: When it is your turn, you can choose cards to play be typing their index.
To play the     cards press enter. Press 'T' to chat and 'Q' to quit.
""".strip().replace('\n', ' ')

def main():
    gui = ClientGui()

class ClientGui():

    card_index = '123456789abcdefghijklmnop'
    players = []    # List of dictionaries: {name="chipjack", num_cards=7, status='a'}
    
    def __init__(self, client):
        # sys.stdout.write("\x1b[8;{rows};{cols}t\]".format(rows=SCRN_HEIGHT, cols=SCRN_WIDTH))
        self.client = client
        self.prev_last_play = []
        self.msgs = []
        self.chat_msgs = []
        self.play_history = []
        self.hand = []
        self.play = []
        self.pending_play = queue.Queue()
        self.chatting = False
        self.lock = threading.RLock()
        self.curses_thread = threading.Thread(target=self.curses_wrapper)
        self.curses_thread.start()
    
    def curses_wrapper(self):
        curses.wrapper(self.curses_loop)

    def chat_validator(self, key):
        if key == curses.ascii.NL: # newline/return key pressed
            return curses.ascii.BEL
        elif key == curses.ascii.DEL: # delete pressed
            return curses.KEY_BACKSPACE
        else:
            self.print_msg('Detected {}'.format(key))
            return key

    def curses_loop(self, stdscr):
        self.build_windows(stdscr)
        while 1:
            c = self.play_win.getkey()
            # self.print_msg('Got key {}'.format(ord(c)))
            if c.upper() == 'T':
                # T for Talk/Chat
                curses.curs_set(1) # make cursor visible
                self.chat_box_win.move(0,0)
                text = self.chat_box.edit(self.chat_validator)
                self.chat_box_win.clear()
                self.chat_box_win.refresh()
                text = text.replace('\n', '').replace('\r', '')
                text = text[:63]
                curses.curs_set(0) # make cursor invisible again
                assert(len(text) <= 63)
                self.client.send_msg('[cchat|{}]'.format(text.ljust(63)))
                self.print_msg('Sent chat message: {}'.format(text))
            elif c.upper() == 'Q':
                # Q for quit
                self.client.run = False
                break
            elif c.upper() == 'H':
                # H for help
                help_msgs = [HELP_MSG[i:i+SCRN_WIDTH-5] for i in range(0,
                    len(HELP_MSG), SCRN_WIDTH-5)]
                for msg in help_msgs:
                    self.print_msg(msg)
            elif ord(c) == curses.ascii.NL:
                # Enter key pressed
                self.pending_play.put(self.play)
                self.print_msg('Played {}'.format(
                    self.print_cards(self.play)))
                self.play = []
                self.update_play()
            if c not in self.card_index:
                continue
            i = self.card_index.index(c)
            if i < len(self.hand):
                # take or put back card from hand
                if self.hand[i] in self.play:
                    # remove card from play
                    self.play.remove(self.hand[i])
                else:
                    self.play.append(self.hand[i])
                self.update_play()
            else:
                self.print_msg("Invalid card index")
        
        # cleanup
        curses.curs_set(1)
        curses.endwin()
        subprocess.call("reset", shell=True)


    def update_play(self):
        self.lock.acquire()
        if not self.hand:
            return
        self.play_input_win.addstr(3, 2, 
            self.print_cards(self.play).ljust(PLAY_INPUT_WIDTH - 3))
        self.play_input_win.refresh()
        hand_indexes = [self.hand.index(c) for c in self.play]
        play_str = ''
        for i in range(len(self.hand)):
            if i in hand_indexes:
                play_str += ('^    ')
            else:
                play_str += ('     ')

        self.hand_win.addstr(6, 2, play_str)
        self.hand_win.refresh()
        self.lock.release()

    def update_chat(self, who, msg):
        self.lock.acquire()
        full_msg = "{}: {}".format(who.strip(), msg.strip())
        if (len(full_msg) > CHAT_WIDTH - 4):
            self.chat_msgs.append(full_msg[:CHAT_WIDTH-4])
            self.chat_msgs.append("    " + full_msg[CHAT_WIDTH-4:])
        else:
            self.chat_msgs.append("{}: {}".format(who.strip(), msg.strip()))
        i = PLAY_CHAT_HEIGHT - 2
        for msg in reversed(self.chat_msgs):
            self.chat_win.addstr(i, 2, msg[:CHAT_WIDTH-4].ljust(CHAT_WIDTH-4))
            i -= 1
            if i == 1:
                break
        self.chat_win.refresh()
        self.lock.release()
        

    def build_windows(self, stdscr):
        self.lock.acquire()
        stdscr.clear()
        title = "WARLORDS AND SCUMBAGS"
        top_right = "H - HELP, Q - QUIT"
        curses.curs_set(0)  # make cursor invisible
        stdscr.addstr(0, 1, title.ljust(SCRN_WIDTH - len(top_right) - 2) +
            top_right)
        stdscr.refresh()
        self.msgs_win = curses.newwin(MSGS_HEIGHT-1, SCRN_WIDTH, 1, 0)
        self.table_win = curses.newwin(TABLE_HEIGHT, SCRN_WIDTH - LOBBY_WIDTH, 
            MSGS_HEIGHT, 0)
        self.lobby_win = curses.newwin(TABLE_HEIGHT + HAND_HEIGHT, LOBBY_WIDTH, 
            MSGS_HEIGHT, SCRN_WIDTH - LOBBY_WIDTH)
        self.hand_win = curses.newwin(HAND_HEIGHT, HAND_WIDTH, 
            MSGS_HEIGHT + TABLE_HEIGHT, 0)
        self.play_win = curses.newwin(PLAY_CHAT_HEIGHT, PLAY_WIDTH,
            MSGS_HEIGHT + TABLE_HEIGHT + HAND_HEIGHT, 0)
        self.chat_win = curses.newwin(PLAY_CHAT_HEIGHT, CHAT_WIDTH,
            MSGS_HEIGHT + TABLE_HEIGHT + HAND_HEIGHT, PLAY_WIDTH)
        self.play_input_win = curses.newwin(INPUT_HEIGHT,
            PLAY_INPUT_WIDTH,
            MSGS_HEIGHT + TABLE_HEIGHT + HAND_HEIGHT + PLAY_CHAT_HEIGHT, 0)
        self.beat_win = curses.newwin(INPUT_HEIGHT, BEAT_WIDTH,
            MSGS_HEIGHT + TABLE_HEIGHT + HAND_HEIGHT + PLAY_CHAT_HEIGHT, 
            PLAY_INPUT_WIDTH)
        self.chat_input_win = curses.newwin(INPUT_HEIGHT, SEND_CHAT_WIDTH,
            MSGS_HEIGHT + TABLE_HEIGHT + HAND_HEIGHT + PLAY_CHAT_HEIGHT,
            PLAY_INPUT_WIDTH + BEAT_WIDTH)
        self.chat_box_win = curses.newwin(INPUT_HEIGHT - 3, SEND_CHAT_WIDTH - 4,
            MSGS_HEIGHT + TABLE_HEIGHT + HAND_HEIGHT + PLAY_CHAT_HEIGHT + 2,
            PLAY_INPUT_WIDTH + BEAT_WIDTH + 2)
        self.chat_box = curses.textpad.Textbox(self.chat_box_win,
            insert_mode=True)

        self.windows = [self.msgs_win, self.table_win, self.lobby_win,
            self.hand_win, self.play_win, self.beat_win, self.chat_win, 
            self.play_input_win, self.chat_input_win]

        self.msgs_win.addstr(1, 2, 'CLIENT LOG MESSAGES')
        self.table_win.addstr(1, 2, 'PLAYERS AT TABLE')
        self.table_win.addstr(2, 2, 'Name'.ljust(12) + 'Card Count'.ljust(14)
            + 'Status'.ljust(10) + 'Strikes')
        self.lobby_win.addstr(1, 2, 'LOBBY')
        self.hand_win.addstr(1, 2, 'HAND')
        self.play_win.addstr(1, 2, 'PLAY HISTORY')
        self.beat_win.addstr(1, 2, 'CARDS TO BEAT')
        self.chat_win.addstr(1, 2, 'CHAT')
        self.play_input_win.addstr(1, 2, 'PLAY CARDS')
        self.chat_input_win.addstr(1, 2, 'SEND CHAT MESSAGE (press \'t\')')

        for win in self.windows:
            win.border()
            win.refresh()
        self.lock.release()

    def print_msg(self, msg):
        self.lock.acquire()
        self.msgs.append(msg)
        i = MSGS_HEIGHT - 3
        for msg in reversed(self.msgs):
            self.msgs_win.addstr(i, 2, msg[:SCRN_WIDTH-4].ljust(SCRN_WIDTH-4))
            i -= 1
            if i == 1:
                break
        self.msgs_win.refresh()
        self.lock.release()

    def print_card(self, card):
        assert(card >= 0 and card < 52)
        suites = [
            '\u2663',   # clubs
            '\u2666',   # diamonds
            '\u2665',   # hearts
            '\u2660',   # spades
        ]
        values = ['3','4','5','6','7','8','9','10','J','Q','K','A','2']

        suite = suites[card % 4]
        value = values[card // 4]

        return value + suite

    def print_cards(self, cards):
        if not cards:
            return ''
        return '   '.join([self.print_card(card) for card in cards])

    def print_hand(self, hand):
        self.lock.acquire()
        if not hand:
            self.hand_win.addstr(3, 2, ' '.ljust(HAND_WIDTH - 3))
            self.hand_win.addstr(5, 2, ' '.ljust(HAND_WIDTH - 3))
            self.hand_win.refresh()
            self.lock.release()
            return
        hand.sort()
        self.hand = hand
        if not hand:
            return
        # self.hand_win.addstr(1, 2, 'HAND')
        self.hand_win.addstr(3, 2, 
            '    '.join([self.card_index[x] for x in range(0,len(hand))]).ljust(
                HAND_WIDTH-3))
        self.hand_win.addstr(5, 2, self.print_cards(hand).ljust(HAND_WIDTH-3))
        self.hand_win.refresh()
        self.lock.release()

    def prompt_for_play(self, player_stat_list, hand, msg=None):
        # deprecated
        if msg:
            self.print_msg(msg)
            # print(msg)

        # for i, ps in enumerate(player_stat_list):
        #    print(('Player {i}: {name}, cards remaining: {num_cards}, status: ' +
        #            '{status}').format(i=i, name=ps.name,
        #                num_cards=ps.num_cards, status=ps.status))

        hand = list(hand)
        hand.sort()
        self.print_msg("It's your turn!")
        # print("It's your turn.\n Your hand: {}".format(self.print_hand(hand)))
        # print("What would you like to play? (use index into card list)")
        play = None 
        if not play:
            return ''
        play = [int(x) for x in play.split(',')]
        play = [hand[x-1] for x in play]
        return(play)

    def update_players(self, player_stat_list):
        self.lock.acquire()
        psl = player_stat_list
        for i, p in enumerate(psl):
            self.table_win.addstr(i+3, 2, '{}{}{}{}'.format(p.name.ljust(12), 
                str(p.num_cards).ljust(14), p.status.ljust(10), str(p.strikes)))
        self.table_win.refresh()
        self.lock.release()

    def update_plays(self, name, play, cards=None):
        if cards:
            self.play_history.append('{} {} {}'.format(name, play,
                self.print_cards(cards)).ljust(PLAY_WIDTH-3))
        else:
            self.play_history.append('{} {}'.format(name, play).ljust(
                PLAY_WIDTH-3))
        i = PLAY_CHAT_HEIGHT - 2
        for play in reversed(self.play_history):
            self.play_win.addstr(i, 2, play)
            i -= 1
            if i == 1:
                break
        self.play_win.refresh()

    def update_play_to_beat(self, play):
        self.lock.acquire()
        self.beat_win.addstr(3, 2, self.print_cards(play).ljust(BEAT_WIDTH - 3))
        self.beat_win.refresh()
        self.lock.release()

    def update(self, player_stat_list, prev_player_stat_list, last_play,
        winner=None, asshole=False):
        self.lock.acquire()

        psl = player_stat_list
        ppsl = prev_player_stat_list

        self.update_players(psl)
        self.update_play_to_beat(last_play)

        whose_turn = client.current_turn_num(psl)
        if ppsl:
            if last_play == []:
                # they won the round
                self.update_plays(psl[whose_turn].name, 'won the round')
                #pass
            elif last_play != self.prev_last_play:
                # someone played some cards, and someone may have been skipped
                who_played = client.current_turn_num(ppsl)
                if who_played == client.current_turn_num(psl):
                    # they must have played a two
                    self.update_plays(psl[who_played].name, 'played a 2')
                    # print('{} played a 2!'.format(psl[who_played].name))
                self.update_plays(psl[who_played].name, 'played', last_play)
                # print('{} played {}'.format(psl[who_played].name, 
                #    self.print_cards(last_play)))
                if ([c // 4 for c in last_play] == 
                    [c // 4 for c in self.prev_last_play]):
                    # someone got skipped
                    self.update_plays('Someone', 'got skipped')
                    # print('Someone got skipped!')
            else:
                # same cards to beat as before, last player must have passed
                # unless the last player played bad cards?
                who_passed = client.current_turn_num(ppsl)
                if client.current_turn_num(psl) == who_passed:
                    # they played bad cards
                    self.print_msg('{} is gonna try that turn again'.format(
                        psl[who_passed].name))
                    #print('{} is gonna try that turn again'.format(
                    #    psl[who_passed].name))
                else:
                    self.update_plays(psl[who_passed].name, 'passed')
                    # print('{} passed'.format(psl[who_passed].name))

        if winner:
            self.update_plays(winner.name, 'has gone out')
            # print("Player {} has gone out!".format(winner.name))
        
        if asshole:
            self.update_plays(asshole.name, 'is the scumbag')
            self.print_msg('Hand over. New hand starting')
        
            # print('Game over. {} is the asshole'.format(asshole.name))
            # self.prev_last_play = []

        self.prev_last_play = last_play
        self.lock.release()
        return False

    def update_lobby(self, lobby):
        self.lock.acquire()
        for i in range(2, LOBBY_HEIGHT):
            self.lobby_win.addstr(i, 2, ' '*(LOBBY_WIDTH-3))
        for i, name in enumerate(lobby[:LOBBY_HEIGHT-3]):
            self.lobby_win.addstr(i+2, 2, name)
        if len(lobby) > LOBBY_HEIGHT - 3:
            self.lobby_win.addstr(LOBBY_HEIGHT-2, 2, '...')
        self.lobby_win.refresh()
        self.lock.release()

if __name__ == '__main__':
    main()
