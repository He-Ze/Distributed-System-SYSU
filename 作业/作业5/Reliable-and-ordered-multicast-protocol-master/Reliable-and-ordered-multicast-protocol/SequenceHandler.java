
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

/**
 * Help class to handle the proposed sequence numbers to a given message
 * @author Julia Gustafsson & Gebrecherkos Haylay 
 *
 */
public class SequenceHandler {
	
	//The message to decide the final sequence number upon
	McGUIMessage mcGuiMessage;
	//A map that stores each proposed sequence number and the peer that propsed the sequence number.
	Map<Integer, Integer> proposedSeqNr;

	public SequenceHandler(McGUIMessage mcGuiMessage){
		this.mcGuiMessage = mcGuiMessage;
		this.proposedSeqNr = new HashMap<Integer, Integer>();
	}

	/**
	 * Save the proposed sequence number and and the proposing peer
	 * @param host - the host that proposed the given sequence number
	 * @param sequenceNr - the proposed sequence number 
	 */
	public void addProposedSeqNr(int host, int sequenceNr){
		proposedSeqNr.put(host, sequenceNr);
	}

	/**
	 * Calculates the largest sequence number from the proposed sequence number
	 * @return the largest proposed sequence number
	 */
	public int getHighestProposedSeqNr(){
		return Collections.max(proposedSeqNr.values());

	}

	/**
	 * Returns true if the compared message has the same message id, sender and text.
	 */
	@Override
	public boolean equals(Object obj) {
		if(obj == null)
			return false;
		if((this == obj))
			return true;
		if (obj instanceof SequenceHandler){
			SequenceHandler m = (SequenceHandler) obj;
			return (mcGuiMessage.getSender() == m.mcGuiMessage.getSender() && m.mcGuiMessage.getMsgID() == mcGuiMessage.getMsgID());
		}else{
			return false;
		}
	}
	/**
	 * Return the hashcode for the message
	 */
	@Override
	public int hashCode(){
		return mcGuiMessage.getSender() + mcGuiMessage.getMsgID();
	}
}
