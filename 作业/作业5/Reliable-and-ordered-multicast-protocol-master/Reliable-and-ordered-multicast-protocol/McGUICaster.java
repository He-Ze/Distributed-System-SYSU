
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

/**
 * Multicast protocol that guuarantees total ordering with preserved casuality, reliable multicasting and failure handling. 
 *
 * @author Julia Gustafsson & Gebrecherkos Haylay
 */
public class McGUICaster extends Multicaster {
	//The message id, that is unique for a given node
	private int msgID = 0;
	//The vector clocks for the node
	private HashMap<Integer, Integer> vectorClock = new HashMap<Integer, Integer>();
	//keep track of all the messages and the proposed sequence numbers.
	private List<SequenceHandler> proposedSequenceNrToMsg = new ArrayList<SequenceHandler>();
	//Comparator used for sorting the list of elements
	private Comparator<McGUIMessage> comparator = new MessageComparator();
	//The set of messages to be decide a final sequence number upon, and eventually deliverer.
	private HashSet<McGUIMessage> toBeDeliveredSet = new HashSet<McGUIMessage>();
	//A list of the peers that are down
	private List<Integer> peersDown = new ArrayList<Integer>();
	//The messages that already has been delivered.
	private HashMap<Integer, McGUIMessage> deliverMap = new HashMap<Integer, McGUIMessage>(); 
	//The messages that has been received
	private List<McGUIMessage> received = new ArrayList<McGUIMessage>();
	/**
	 * Initiaze the vector clocks
	 */
	public void init() {
		mcui.debug("The network has "+hosts+" hosts!");
		for(int i=0; i < hosts; i++) {
			vectorClock.put(i, 0);
		}

	}

	/**
	 * The given text will be sent to the peers as a message with the proposed sequence number 
	 * @param messagetext  The message text to send
	 */
	public void cast(String messagetext) {
		//Make a new message with the given text, and an updated message id and the proposed sequence number.
		msgID = msgID + 1;
		//The proposed sequence number is based on the current largest vector clock value
		int proposedSequenceNr = getLargestVectorClock() + 1;
		McGUIMessage newMsg = new McGUIMessage(id, msgID, messagetext, proposedSequenceNr);
		sendMsg(newMsg);
		//Add the new message to set of messages to be delivered 
		toBeDeliveredSet.add(newMsg); 
		//Make a new instance of the help class to keep track of proposed sequence numbers. The senders own 
		//proposed priority is added to the instance.
		SequenceHandler seqHelp = new SequenceHandler(newMsg);
		seqHelp.addProposedSeqNr(id, proposedSequenceNr);
		proposedSequenceNrToMsg.add(seqHelp);
		//Local vector clock for the node is updated.
		vectorClock.put(id, proposedSequenceNr);		
		received.add(newMsg);
	}

	/**
	 * Send the message to all other hosts
	 * @param msg - the message to be sent
	 */
	public void sendMsg(McGUIMessage msg){
		for(int i=0; i < hosts; i++) {
			//Sends to everyone except itself and peers that are down
			if(i != id && !peersDown.contains(i)) {      	
				bcom.basicsend(i, msg);
			}
		}
	}

	/**
	 * Receive a basic message and acts different depending on the sender and the final sequence number of the message.
	 * @param peer - the peer that sent the given message
	 * @param message - the message received from the peer
	 */
	public void basicreceive(int peer,Message message) {
		McGUIMessage msg = (McGUIMessage) message;
		//A node receives a new message that originates from another node and that holds a proposal
		if(msg.getSender() != id && !msg.isDeliverable()){ 
			//If the message has not been received before  it's not a duplicate 
			if(!rec(msg)){
				received.add(msg);
				toBeDeliveredSet.add(msg);
				int proposedSeqNr = getLargestVectorClock() + 1;
				//Flooding, send the messages to the other peers
				for(int i=0; i < hosts; i++) {
					//Sends to everyone except itself and peer that are down
					if(i != id && !peersDown.contains(i) && i != msg.sender && i != peer) {      	
						bcom.basicsend(i, msg);
					}
				}

				//Update the local vector clocks for the sender of the message.
				updateVectorClock(msg.sender, proposedSeqNr);
				//If the peer has proposed a value strictly less than the value the node
				//proposes, the sender misses messages. The missing messages will be retransmitted.
				if(deliverMap.size() > 0 && msg.getSeqNr() < proposedSeqNr){
					retransmitMsgs(msg.sender, msg.getSeqNr(),proposedSeqNr);
				}
				msg.setSeqNr(proposedSeqNr);
				//McGUIMessage m = new McGUIMessage(msg.sender, msg.getMsgID(), msg.getText(),proposedSeqNr);
				bcom.basicsend(msg.getSender(), msg);
			}
		}
		//Sender of a message receives another node's response to the message, with a proposed sequence number.
		else if(msg.getSender() == id && rec(msg)){
			SequenceHandler seqHandler = getProposedSequenceNrAndNodes(msg);
			//Only continue to operate if the corresponding SequenceHandler instance to the message exist 
			if(seqHandler != null){
				//Save the sequence number and corresponding peer to the corresponding help class to the message.
				seqHandler.addProposedSeqNr(peer, msg.getSeqNr());
				//If all other nodes has proposed a sequence nr to the message, a final sequence number can be set.
				if(seqHandler.proposedSeqNr.size() == (hosts  - peersDown.size())){
					int finalSeqNr = seqHandler.getHighestProposedSeqNr();
					msg.setSeqNr(finalSeqNr);
					msg.setDeliverable(true);
					retransmitMsgsToGroup(seqHandler, finalSeqNr);
					//Remove the help class to the message, as the final sequence nr is decided
					proposedSequenceNrToMsg.remove(seqHandler);
					sendMsg(msg);
					deliverMessage(id, msg);
				}
			}
		}
		//A node receives the message with the final sequence number set.
		else if(msg.isDeliverable()){
			deliverMessage(peer, msg);
		}
	}



	/**
	 * Iterate through the answer and retransmit old messages, if a peer seems to have missed some messages
	 * @param seqHandler - The sequencehandler instance for a given message
	 * @param SeqNr - the new largest sequence number
	 */
	public void retransmitMsgsToGroup(SequenceHandler seqHandler, int SeqNr){
		if(deliverMap.size() > 0){
			Map<Integer, Integer> map = seqHandler.proposedSeqNr;
			for (Map.Entry<Integer,Integer> entry : map.entrySet()) {
				//If the peer has suggested a lower sequence nr, which means that it misses some messages.
				if(entry.getValue() < SeqNr){
					retransmitMsgs(entry.getKey(), entry.getValue(), SeqNr);
				}
			}
		}
	}


	/**
	 * 
	 * @param peer - the peer to send the messages to
	 * @param startSeqNr - the smallest sequence number of the first message that should be retransmitted.
	 * @param maxSeqNr - Messages up till the message with sequence number maxSeqNr should be retransmitted
	 */
	public void retransmitMsgs(int peer, int startSeqNr, int maxSeqNr){
		for(int i=startSeqNr; i < maxSeqNr; i++) {
			//Resend the missed message to the peer
			if(i != id && !peersDown.contains(peer) ) {  
				McGUIMessage msg = deliverMap.get(i);
				if(msg != null)
					bcom.basicsend(peer, deliverMap.get(i));
			}

		}
	}

	/**
	 * Update the local vector clock, with the new value for the given peer
	 * - if it larger than the already existing value for the peer
	 * @param peer - the peer's vector clock to be updated
	 * @param value - the new value of the peers vector clock
	 */
	public void updateVectorClock(int peer, int value){
		if(vectorClock.get(peer) < value)
			vectorClock.put(peer, value);
	}

	/**
	 * If possible deliver messages(in the correct order) to the node. This is done by updating the set of messages with the given message, 
	 * update the local vector clock for the given host and sort the list.
	 * @param host - the host who vector clock should be updated
	 * @param msg - the message to be delivered
	 */
	public void deliverMessage(int host, McGUIMessage msg){
		mcui.debug("deliver a message from " + host + " seq " + msg.getSeqNr());
		//If the message msg it successfully removed, then the message is not a duplicate.
		if(toBeDeliveredSet.remove(msg)){ 
			//Flooding, send the message to other peers
			for(int i=0; i < hosts; i++) {
				if(i != id && !peersDown.contains(i) && i != msg.sender && i != host) {      	
					bcom.basicsend(i, msg);
				}
			}
			//Update the vectorclock for the given host with the final sequence nr for the given message msg
			updateVectorClock(host, msg.getSeqNr());
			//Update the message to deliverable
			msg.setDeliverable(true);
			//Save the modified message msg to the set of messages to be delivered again 
			toBeDeliveredSet.add(msg);
			//Sort the messages that is in set of messages to be delivered 
			final List<McGUIMessage> sorted = new ArrayList<McGUIMessage>(toBeDeliveredSet);
			Collections.sort(sorted, new MessageComparator());
			boolean canDeliver = true;
			int index = 0;
			//As long as messages can be delivered, the list isn't empty and the list still has more indexes to check
			//messages in the sorted list will be delivered. 
			McGUIMessage first = null; 
			while(canDeliver && !sorted.isEmpty() && index < sorted.size()){
				first = sorted.get(index);
				if(first.isDeliverable()){
					mcui.deliver(first.getSender(), first.getText(), "from " + first.getSender() + "seq " + first.getSeqNr());
					//Remove from the set of messages tobe delivered
					toBeDeliveredSet.remove(first);
					//Add to list of delivered messages 
					deliverMap.put(first.getSeqNr(), first);
					index = index + 1;

				}else if(peersDown.contains(first.sender) && !first.isDeliverable()){
					toBeDeliveredSet.remove(first);
				}else{
					canDeliver = false;
				}
			}

		}
	}

	/**
	 * Find out if the messages has been delivered or not
	 * @param msg
	 * @return
	 */
	public boolean valueExists(McGUIMessage msg){
		for(McGUIMessage m: deliverMap.values()){
			if(msg.sender == m.sender && msg.getMsgID() == m.getMsgID())
				return true;
		}
		return false;
	}

	/**
	 * Find the message in the list of SequenceHandler instances that corresponds to the given message
	 * @param msg - the given message
	 * @return  the corresponding SequenceHandler instance for that message
	 */
	public SequenceHandler getProposedSequenceNrAndNodes(McGUIMessage msg){
		for(SequenceHandler proposedprioritymsg: proposedSequenceNrToMsg){
			if(proposedprioritymsg.mcGuiMessage.getSender() == msg.getSender() && proposedprioritymsg.mcGuiMessage.getMsgID() == msg.getMsgID())
				return proposedprioritymsg;
		}
		return null;
	}

	/**
	 * Find out if the message has been received or not
	 * @param msg
	 * @return
	 */
	public boolean rec(McGUIMessage msg){
		for(McGUIMessage r: received){
			if(r.getSender() == msg.getSender() && r.getMsgID() == msg.getMsgID())
				return true;
		}
		return false;
	}

	/**
	 * Calculates the largest value in the local vector clock
	 * @return the largest vector clock
	 */
	public int getLargestVectorClock(){
		return Collections.max(vectorClock.values());

	}

	/**
	 * Signals that a peer is down and has been down for a while to
	 * allow for messages taking different paths from this peer to
	 * arrive.
	 * @param peer	The dead peer
	 */
	public void basicpeerdown(int peer) {
		peersDown.add(peer);
		//Remove the peer and its corresponding that are down from each list of proposed sequence nr from the help classes to messages.
		for(SequenceHandler msg: proposedSequenceNrToMsg){
			for(int p : peersDown)
				msg.proposedSeqNr.remove(p);
		}
		List<McGUIMessage> lista = new ArrayList<McGUIMessage>();
		List<McGUIMessage> remove = new ArrayList<McGUIMessage>();
		Iterator<McGUIMessage> iter = toBeDeliveredSet.iterator();
		while (iter.hasNext()) {
			McGUIMessage msg =	(McGUIMessage) iter.next();
			if(msg.sender == id && !msg.isDeliverable()){
				mcui.debug("first sender == 2015");
				SequenceHandler seqHandler = getProposedSequenceNrAndNodes(msg);
				if(seqHandler != null){
					mcui.debug("seqhandler !=null");			
					if((seqHandler.proposedSeqNr.size()) >= (hosts- peersDown.size())){
						mcui.debug("(deliver!");
						int finalSeqNr = seqHandler.getHighestProposedSeqNr();
						//Remove the help class to the message, as the final sequence nr is decided
						proposedSequenceNrToMsg.remove(seqHandler);
						retransmitMsgsToGroup(seqHandler, finalSeqNr);
						McGUIMessage mc = new McGUIMessage(id, msg.getMsgID(), msg.getText(), finalSeqNr);
						mc.deliverable = true;
						for(int i=0; i < hosts; i++) {
							//Sends to everyone except itself and peers that are down
							if(i != id && !peersDown.contains(i)) {      	
								bcom.basicsend(i, mc);
							}
						}
						lista.add(mc);

					}
				}
			}else if(msg.sender == peer && !msg.isDeliverable()){
				//Remove msgs that will never get a final sequence nr
				remove.add(msg);
			}
		}

		//Remove msgs
		for(McGUIMessage mc : remove){
			toBeDeliveredSet.remove(mc);
			//Remove Sequence handler for messages to remove
			SequenceHandler seqHandler = getProposedSequenceNrAndNodes(mc);
			if(seqHandler != null){
				proposedSequenceNrToMsg.remove(seqHandler);
			}
		}
		//Deliver msgs
		for(McGUIMessage mc : lista)
			deliverMessage(id, mc);

		mcui.debug("DONE peersdown handling");
	}

}
