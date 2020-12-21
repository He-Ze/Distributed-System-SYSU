

import java.util.Comparator;

/**
 * A class that compares McGUIMessage-messages in order to sort them according to their deliverable status and final sequence number
 * @author Julia Gustafsson & Gebrecherkos Haylay
 *
 */
public class MessageComparator implements Comparator<McGUIMessage>{

	/**
	 * Sort messages according to their  sequence number.
	 */
	@Override
	public int compare(McGUIMessage msg1, McGUIMessage msg2) {
		
			if(msg1.getSeqNr() > msg2.getSeqNr())
				return 1;
			else if(msg1.getSeqNr() < msg2.getSeqNr())
				return -1;
			else 
				return 0; 
		
	}
	

	
}
