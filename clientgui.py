import message
import client


class ClientGui():

    players = []    # List of dictionaries: {name="chipjack", num_cards=7, status='a'}
    
    def __init__(self):
        print("Initializing game, waiting for players.")
        self.prev_last_play = []

    def print_msg(self, msg):
        print(msg)

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
        return ' , '.join([self.print_card(card) for card in cards])

    def print_hand(self, hand):
        if not hand:
            return ''
        return ' , '.join([str(index + 1) + '-' + self.print_card(card) for index, card in enumerate(hand)])

    def prompt_for_play(self, player_stat_list, hand, msg=None):
        if msg:
            print(msg)

        for i, ps in enumerate(player_stat_list):
            print(('Player {i}: {name}, cards remaining: {num_cards}, status: ' +
                    '{status}').format(i=i, name=ps.name,
                        num_cards=ps.num_cards, status=ps.status))

        hand = list(hand)
        hand.sort()
        print("It's your turn.\n Your hand: {}".format(self.print_hand(hand)))
        print("What would you like to play? (use index into card list)")
        play = input('--> ')
        if not play:
            return ''
        play = [int(x) for x in play.split(',')]
        play = [hand[x-1] for x in play]
        return(play)

    def update(self, player_stat_list, prev_player_stat_list, last_play,
        winner=None, asshole=False):

        psl = player_stat_list
        ppsl = prev_player_stat_list

        if ppsl:
            if last_play == []:
                # they won the round
                pass
            elif last_play != self.prev_last_play:
                # someone played some cards, and someone may have been skipped
                who_played = client.current_turn_num(ppsl)
                if who_played == client.current_turn_num(psl):
                    # they must have played a two
                    print('{} played a 2!'.format(psl[who_played].name))
                print('{} played {}'.format(psl[who_played].name, 
                    self.print_cards(last_play)))
                if ([c // 4 for c in last_play] == 
                    [c // 4 for c in self.prev_last_play]):
                    # someone got skipped
                    print('Someone got skipped!')
            else:
                # same cards to beat as before, last player must have passed
                # unless the last player played bad cards?
                who_passed = client.current_turn_num(ppsl)
                if client.current_turn_num(psl) == who_passed:
                    # they played bad cards
                    print('{} is gonna try that turn again'.format(
                        psl[who_passed].name))
                else:
                    print('{} passed'.format(psl[who_passed].name))

        if winner:
            print("Player {} has gone out!".format(winner.name))
        
        if asshole:
            print('Game over. {} is the asshole'.format(asshole.name))
            self.prev_last_play = []

        self.prev_last_play = last_play
        return False

    def update_lobby(self, lobby):
        print("Lobby updated: {}".format(', '.join(lobby)))


