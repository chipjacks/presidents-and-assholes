from random import shuffle
import logging

HOST = 'localhost'
PORT = 36716
TABLESIZE = 7
LOBBYSIZE = 35

def setup_logging():
    FORMAT = '%(filename)s: %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=FORMAT)
    logging.info('Logging started')

class Deck:
    """
    A deck of cards, which can be shuffled and dealt.
    """
    DECK_SIZE = 52
    
    def __init__(self):
        self.cards = [x for x in range(self.DECK_SIZE)]
    
    def shuffle(self):
        shuffle(self.cards)
    
    def deal(self, numplayers):
        self.shuffle()
        handsize = self.DECK_SIZE // numplayers
        hands = [self.cards[i*handsize:(i+1)*handsize] 
            for i in range(numplayers)]
        for i in range(self.DECK_SIZE - handsize * numplayers):
            hands[i].append(self.cards[-1-i])
        return hands

class Player:
    """
    A player who has a hand of cards and can play cards on table.
    """
    def __init__(self, name):
        self.hand = []
        self.name = name
        self.status = 'l'
        self.strikes = 0

    def pickup_hand(self, cards):
        self.clear_hand()
        self.add_to_hand(cards)

    def add_to_hand(self, cards):
        assert(isinstance(cards, list))
        for i in cards:
            assert(i >= 0 and i <= 51)
        self.hand += cards
        hand_set = set(self.hand)
        assert(len(self.hand) == len(hand_set))
    
    def clear_hand(self):
        self.hand = []

    def remove_from_hand(self, cards):
        if not cards:
            return
        assert(isinstance(cards, list))
        cards = set(cards)
        hand_set = set(self.hand)
        if (not cards <= hand_set):
            raise PlayerError(self, "tried to remove cards they don't have from hand")
        for card in cards:
            self.hand.remove(card)

class Table:
    def __init__(self):
        self.players = []
        self.winners = []
        self.played_cards = []
        self.turn = 0
        self.starting_round = True
        self.deck = Deck()

    def add_player(self, player):
        assert(isinstance(player, Player))
        if self.full():
            return False
        else:
            self.players.append(player)
            return True
    
    def active_players(self):
        active_players = []
        for player in self.players:
            if player.status in ('a','w','p') and len(player.hand) > 0:
                active_players.append(player)
        return active_players

    def last_play(self):
        if not self.played_cards:
            return None
        else:
            return self.played_cards[-1]

    def deal(self):
        hands = self.deck.deal(len(self.players))
        assert(len(self.players) == len(hands))
        for i, player in enumerate(self.players): 
            player.pickup_hand(hands[i])
        return hands

    def remove_player(self, player):
        assert(isinstance(player, Player))
        self.players.remove(player)

    def play_cards(self, player, cards):
        assert(isinstance(cards, list))
        assert(len(self.players) > 1) # make sure the game should still be going
        # validate play
        self.validate_play(player, cards)

        # did they pass or play?
        if not cards:
            player.status = 'p'
        else:
            self.played_cards.append(cards)
            player.remove_from_hand(cards)
            player.status = 'w'
            if len(player.hand) == 0:
                # they won!
                logging.info('%s won!', player.name)
                self.winners.append(player)
        active_players = self.active_players()
        if len(active_players) <= 1:
            # the game is over
            return
        # who is next?
        if cards and cards[0] >= 48:
            # the player played a 2 and gets to go again, unless he is out
            if player in self.winners:
                # he is out, it's next players turn
                player.status = 'w'
                self.turn += 1
                self.turn %= len(active_players)
                active_players[self.turn].status = 'a'
            else:
                # he is still playing, it's his turn
                player.status = 'a'
            self.played_cards.append([])
        else:
            # see if anyone got skipped
            if (player.status == 'w' and len(self.played_cards) >= 2 and
                    [c // 4 for c in self.played_cards[-2]] == 
                    [c // 4 for c in cards]):
                # someone did get skipped
                self.turn += 1
                self.turn %= len(active_players)
                active_players[self.turn].status = 'p'
                logging.info('skipping %s', active_players[self.turn].name)
            # it's next players turn
            self.turn += 1
            self.turn %= len(active_players)
            active_players[self.turn].status = 'a'
            # see if everyone has passed
            for player in active_players:
                assert(player.status not in ('e', 'd'))
                if player.status == 'w':
                    # they have played this round
                    break
            else:
                # everyone has passed, new round
                self.played_cards.append([])

    def full(self):
        return (len(self.players) >= TABLESIZE)

    def ready(self):
        return (len(self.players) > 2)

    def validate_play(self, player, cards):
        assert(isinstance(cards, list))
        # make sure no duplicate cards in list
        cards_set = set(cards)
        if len(cards_set) != len(cards):
            raise PlayerError(player, "played duplicates of a card", '17')

        # check the player is in turn and has the cards
        if player not in self.players:
            raise PlayerError(player, "tried to play cards when not at table", '31')
        for card in cards:
            if card not in player.hand:
                raise PlayerError(player, "tried to play cards they don't have: {}, {}".format(str(card), repr(player.hand)), '14')
        if player.status != 'a':
            raise PlayerError(player, "tried to play when not his turn", '15')

        if len(cards) == 0:
            # they passed
            return
        if len(cards) > 1:
            # check that they are all the same number
            for card in cards:
                if card // 4 != cards[0] // 4:
                    raise PlayerError(player, "sent cards that don't have matching face value", '11')

        # check that it beats last play
        if self.played_cards == [] or self.played_cards[-1] == []:
            # last play is empty, this play is valid
            return
        elif cards[0] // 4 == 12:
            # they played a 2
            return
        else:
            last_play = self.played_cards[-1]
            if cards[0] // 4 < last_play[0] // 4:
                raise PlayerError(player, "sent cards with too low of a face value", '12')
            elif len(cards) < len(last_play):
                raise PlayerError(player, "played cards without too low of a quantity", '13')
        return

class GameError(Exception):
    pass

class PlayerError(GameError):
    """
    Exception raised when players perform invalid actions
    
    Attributes:
        player -- player who caused exception
        msg -- what the player did wrong

    e.g. "Player JohnD: invalid cards played"
    """
    def __init__(self, player, msg, strike_code='00'):
        self.player = player
        self.msg = msg
        self.strike_code = strike_code

    def __str__(self):
        return "Player {}: {}".format(self.player.name, self.msg)

if __name__ == '__main__':
    d = Deck()

